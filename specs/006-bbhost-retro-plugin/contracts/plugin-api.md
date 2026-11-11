# Interface Contract: bbhost Retro Plugin (`lowpoly_overhaul.so`)

**Feature**: `006-bbhost-retro-plugin`
**API Version**: `BB_PLUGIN_API_VERSION 28`

## Exported Plugin Symbols

The shared library `plugins/lowpoly_overhaul.so` exports standard C symbols conforming to `include/bbhost_plugin.h`:

```c
#include "bbhost_plugin.h"

BB_PLUGIN_EXPORT const BbPluginInfo bb_plugin_info = {
    .version = BB_PLUGIN_API_VERSION,
    .flags   = BB_PLUGIN_OPT_IN | BB_PLUGIN_LIVE_SWITCH,
    .name    = "lowpoly_overhaul",
    .title   = "Bloodborne Low Poly Overhaul Shaders",
    .version_str = "1.0.0",
    .author  = "Bloodborne Demake Team",
    .desc    = "Authentic 32-bit PSX graphics emulation: vertex coordinate snapping, affine texture mapping, and luminance-locked 4x4 Bayer dithering."
};

BB_PLUGIN_EXPORT const BbOption bb_plugin_options[] = {
    {BB_OPT_BOOL | BB_OPT_LIVE, "enabled", "Enable Low-Poly Shaders", "Master toggle for 32-bit graphics pipeline.", "true"},
    {BB_OPT_CHOICE | BB_OPT_LIVE, "snap", "Vertex Snapping", "Grid coordinate jitter intensity.", "240p", 0, 0, "Off|480p|360p|240p|120p"},
    {BB_OPT_BOOL | BB_OPT_LIVE, "affine", "Affine Texture Mapping", "Perspective-incorrect UV mapping (NoPerspective).", "true"},
    {BB_OPT_BOOL | BB_OPT_LIVE, "dither", "Luminance Bayer Dither", "15-bit color dithering with locked chroma ratio.", "true"},
    {BB_OPT_BOOL | BB_OPT_LIVE, "point_filter", "Point Texture Filtering", "Disables bilinear smoothing for sharp texels.", "true"},
    {BB_OPT_BOOL | BB_OPT_LIVE, "colour_8bit", "8-Bit Color Targets", "Quantizes lighting buffers to RGBA8.", "true"},
    {0}
};

BB_PLUGIN_EXPORT int bb_plugin_init(const BbHostApi* api);
BB_PLUGIN_EXPORT int bb_plugin_image(const BbHostApi* api);
```

## Render Hook Contract (`on_render`)

The plugin registers a compute hook at point `BB_RENDER_AFTER_UPSCALE`:

```c
void on_render_callback(const BbRenderCall* call, void* user);
```

### Constraints:
- Invoked outside of active render passes with the renderer lock held.
- Operates exclusively on compute and transfer queues (`VkCommandBuffer` provided in `call->command_buffer`).
- Dispatches luminance Bayer dither shader reading from `call->picture` and writing back dithered output.
- Must execute with sub-millisecond execution latency (< 0.2 ms on GTX 1650).

## Shader Interception Contract (`shader_override`)

For affine texture mapping:
- Intercepts pixel shaders declaring `struct StageInput` via `api->shader_source`.
- Prepends `noperspective` interpolators to input attribute lines:
  ```hlsl
  // Input:
  float4 uv : TEXCOORD0;
  // Transformed:
  noperspective float4 uv : TEXCOORD0;
  ```
- Submits patched HLSL string back to `api->shader_override(plugin_name, shader_name, patched_source)`.

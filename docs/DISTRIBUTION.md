# Distribution & Patch Packaging Workflow

This document details the generation, verification, and deployment of legal differential XOR patch packages for GitHub Releases.

---

## 1. Compliance & Distribution Principles

1. **Zero Copyrighted Asset Redistribution**: Never distribute proprietary FromSoftware assets, DCX containers, or decompressed binaries directly.
2. **Deterministic XOR Differential Containers**: All mod deliveries use byte-level XOR delta streaming against pristine retail `CUSA03173/dvdroot_ps4/`.
3. **Mandatory Output Targeting**: Release scripts must enforce explicit destination directories (`--out`) without relying on ambient runner defaults.

---

## 2. Generating Differential Patches

To compile a `.patch` package from a completed mod folder against the retail baseline:

```bash
uv run python tools/pipeline/create_patch.py \
    --vanilla /path/to/CUSA03173 \
    --mod /path/to/mod_folder \
    --output dist/bloodborne_custom_component.patch \
    --workers 12
```

### Packaging All 5 Modular Pillars:
To generate all 5 modular patch files and the master overhaul containers:
```bash
uv run python tools/pipeline/package_modular_mods.py \
    --vanilla /path/to/CUSA03173 \
    --dist-dir dist/ \
    --workers 12
```

---

## 3. Manifest Verification & Release Artifacts

Whenever `.patch` containers or `apply_patch.py` are updated:

1. Copy the latest reconstructor script to `dist/`:
   ```bash
   cp apply_patch.py dist/apply_patch.py
   ```

2. Recompute the cryptographic checksum manifest:
   ```bash
   cd dist && sha256sum *.patch apply_patch.py > SHA256SUMS.txt
   ```

3. Audit integrity:
   ```bash
   cd dist && sha256sum -c SHA256SUMS.txt
   ```

4. Update `dist/RELEASE_NOTES.md` with file sizes, feature changes, and exact SHA256 digests.

---

## 4. GitHub Release Ingestion

Publishing a new release involves:
- Attaching `dist/*.patch`.
- Attaching `dist/apply_patch.py`.
- Attaching `dist/SHA256SUMS.txt`.
- Copying `dist/RELEASE_NOTES.md` into the release description.

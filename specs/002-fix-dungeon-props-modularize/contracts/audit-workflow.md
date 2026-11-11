# Contract: Multi-Model Audit Workflow

**Feature**: `002-fix-dungeon-props-modularize`  
**Constitution Principle**: Principle VI (Multi-Model Independent Quality Audit)  
**Target Tool**: `tools/pipeline/audit_assets_adversarial.py` and AGY Subagent Protocol  

---

## 1. Audit Execution Protocol

### Step 1: Metric Extraction
```bash
uv run python tools/pipeline/audit_assets_adversarial.py --pillar <PILLAR> --report /tmp/audit_raw.json
```
The extraction tool computes mathematical properties across all modified assets in the stage:
- Maximum triangle edge length across all meshes (threshold: $\le 2.0$m).
- Minimum triangle surface area (threshold: $\ge 10^{-6}$ m$^2$).
- Maximum aspect ratio $\rho$ (threshold: $\le 25.0$).
- Decimation reduction percentage (threshold: $70\%\text{--}80\%$).
- Flat normal facet verification (`norm_diff > 0` across coplanar faces).
- Havok collision file `.hkx` presence and integrity.

### Step 2: Adversarial Audit Invocation
The main agent invokes an independent auditor subagent:
```json
{
  "TypeName": "research",
  "Role": "Independent Quality Auditor",
  "Prompt": "Perform adversarial audit of props demake and modular packaging outputs from /tmp/audit_raw.json. Verify absence of exploded vertices, verify cage decimation, verify 5-pillar folder boundaries. Output signed PASS/FAIL report."
}
```

### Step 3: Audit Sign-Off Report (`AUDIT_REPORT.md`)
The auditor subagent outputs a structured markdown report:
- `Auditor`: Model identifier (e.g. Sonnet 4.6 / Pro agent).
- `Pillars Audited`: Maps, Props, Armors, Characters, HUD.
- `Gate Verdict`: **PASS** or **FAIL**.
- If any check fails, pipeline halts and reports offending asset IDs.

"""
Instant Btrfs / File Restore from clean CUSA03173 to CUSA03173-PSX.
"""

import os, sys, shutil, glob
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parent.parent
CUSA_CLEAN = str(REPO_ROOT / 'CUSA03173')
CUSA_PSX   = str(REPO_ROOT / 'CUSA03173-PSX')

def restore_file(rel_path: str):
    src = os.path.join(CUSA_CLEAN, rel_path)
    dst = os.path.join(CUSA_PSX, rel_path)
    if not os.path.exists(src):
        print(f"Error: Source not found: {src}")
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    print(f"[RESTORED] {rel_path}")
    return True

def restore_targets(targets: list[str]):
    for t in targets:
        restore_file(t)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        restore_targets(sys.argv[1:])
    else:
        # Default: restore key character and part files
        key_files = [
            'dvdroot_ps4/chr/c8030.chrbnd.dcx',
            'dvdroot_ps4/parts/bd_a_9700.partsbnd.dcx',
            'dvdroot_ps4/parts/bd_a_9709.partsbnd.dcx',
            'dvdroot_ps4/parts/bd_m_9300.partsbnd.dcx',
            'dvdroot_ps4/parts/bd_f_9300.partsbnd.dcx',
            'dvdroot_ps4/parts/bd_a_9309.partsbnd.dcx',
            'dvdroot_ps4/parts/hd_a_9700.partsbnd.dcx',
            'dvdroot_ps4/parts/hd_a_9709.partsbnd.dcx',
            'dvdroot_ps4/parts/am_a_9700.partsbnd.dcx',
            'dvdroot_ps4/parts/lg_m_9300.partsbnd.dcx',
            'dvdroot_ps4/parts/lg_f_9300.partsbnd.dcx',
        ]
        restore_targets(key_files)

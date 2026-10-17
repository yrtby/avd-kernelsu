#!/usr/bin/env python3
"""
REA maps-scrub patch for fs/proc/task_mmu.c (android14-6.1 / 6.1.23).

Rationale: AppGuard (NHN AppGuard RASP) detects the Android emulator by reading
/proc/self/maps and matching emulator-artifact substrings ("ranchu", "goldfish",
"emulation"/"emu") in the mapped file paths (libEGL_emulation.so,
graphics.mapper@3.0-impl-ranchu.so, libGoldfishProfiler.so, libandroidemu.so,
EmulationPixel6Overlay.apk, qemu property-context mappings, ...). These libraries
are fundamental to the emulator's graphics stack and inherited from Zygote, so
they cannot be removed without breaking graphics.

This patch scrubs those substrings from the *display* of /proc/*/maps (and smaps,
which shares show_map_vma) with same-length neutral bytes. The real file paths,
library loading, dependency resolution, and HAL behaviour are untouched — only
what userspace reads back from the maps file changes. No struct/header/exported
symbol changes => module CRCs (module_layout) are unaffected => the AVD's own
6.1.23 vendor modules (goldfish_pipe, virtio_gpu, ...) still load.
"""
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "kernel/common/fs/proc/task_mmu.c"

HELPER = (
    "/* REA: scrub emulator-artifact substrings from /proc/*/maps path display */\n"
    "static void rea_scrub_path(char *s, size_t n)\n"
    "{\n"
    "\tstatic const char * const rea_kw[] = { \"emu\", \"goldfish\", \"ranchu\" };\n"
    "\tsize_t i, k, kl;\n"
    "\n"
    "\tfor (k = 0; k < ARRAY_SIZE(rea_kw); k++) {\n"
    "\t\tkl = strlen(rea_kw[k]);\n"
    "\t\tif (n < kl)\n"
    "\t\t\tcontinue;\n"
    "\t\tfor (i = 0; i + kl <= n; i++) {\n"
    "\t\t\tif (strncasecmp(s + i, rea_kw[k], kl) == 0) {\n"
    "\t\t\t\tmemset(s + i, 'x', kl);\n"
    "\t\t\t\ti += kl - 1;\n"
    "\t\t\t}\n"
    "\t\t}\n"
    "\t}\n"
    "}\n"
    "\n"
)

MARKER = (
    "static void\n"
    "show_map_vma(struct seq_file *m, struct vm_area_struct *vma)\n"
    "{"
)

OLD = (
    "\tif (file) {\n"
    "\t\tseq_pad(m, ' ');\n"
    "\t\tseq_file_path(m, file, \"\\n\");\n"
    "\t\tgoto done;\n"
    "\t}"
)

NEW = (
    "\tif (file) {\n"
    "\t\tseq_pad(m, ' ');\n"
    "\t\t{\n"
    "\t\t\tsize_t rea_pos = m->count;\n"
    "\t\t\tseq_file_path(m, file, \"\\n\");\n"
    "\t\t\tif (!seq_has_overflowed(m) && m->count > rea_pos)\n"
    "\t\t\t\trea_scrub_path(m->buf + rea_pos, m->count - rea_pos);\n"
    "\t\t}\n"
    "\t\tgoto done;\n"
    "\t}"
)


def main():
    with open(PATH, "r", encoding="utf-8") as f:
        src = f.read()

    if "rea_scrub_path" in src:
        print("already patched; nothing to do")
        return 0

    if MARKER not in src:
        print("ERROR: show_map_vma marker not found", file=sys.stderr)
        return 1
    if OLD not in src:
        print("ERROR: file-branch block not found", file=sys.stderr)
        return 1

    src = src.replace(MARKER, HELPER + MARKER, 1)
    src = src.replace(OLD, NEW, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)

    print("OK: patched %s" % PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())

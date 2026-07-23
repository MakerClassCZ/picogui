#!/usr/bin/env python3
# Generate the circup bundle metadata JSON for picogui.
#
# circuitpython-build-bundles builds correct zips, but its own JSON keys every package by the GIT
# REPO name -- so a repo that ships many modules (like this one) collapses to a single surviving
# entry. circup then only sees one installable module. This script rebuilds the JSON keyed by the
# real MODULE name, one entry per file, with intra-bundle dependencies discovered from the imports.
#
# Usage: gen_bundle_json.py <libraries_dir> <out.json> <version> <repo_url>
import json, os, re, sys

# matches `import picogui` / `from picogui import ...` AND the picogui_* submodules
IMPORT_RE = re.compile(r"^\s*(?:from\s+(picogui\w*)\s+import|import\s+(picogui\w*))", re.M)


def module_deps(src, known):
    """Return the picogui* modules this source imports, restricted to bundle members."""
    deps = set()
    for m in IMPORT_RE.finditer(src):
        name = m.group(1) or m.group(2)
        if name in known:
            deps.add(name)
    return deps


def main():
    libs_dir, out_path, version, repo = sys.argv[1:5]
    # discover modules: one subfolder per module, holding <name>.py
    modules = {}
    for name in sorted(os.listdir(libs_dir)):
        py = os.path.join(libs_dir, name, name + ".py")
        if os.path.isfile(py):
            with open(py, encoding="utf-8") as f:
                modules[name] = f.read()

    out = {}
    for name, src in modules.items():
        deps = sorted(module_deps(src, modules) - {name})  # never depend on self
        out[name] = {
            "package": False,
            "pypi_name": None,
            "version": version,
            "repo": repo,
            "path": "lib/" + name,
            "dependencies": deps,
            "external_dependencies": [],
            "pypi_description": "",
        }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, sort_keys=True, indent=0)
    print("wrote", out_path, "with", len(out), "modules")


if __name__ == "__main__":
    main()

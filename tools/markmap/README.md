# Local Markmap

Requires Node.js 18 or newer and npm. The CLI is pinned to `markmap-cli@0.18.12` and installed locally in this directory.

From the repository root:

```powershell
npm --prefix tools/markmap ci
npm --prefix tools/markmap run build
```

The build reads `docs/river-engineering-map.md` and writes `docs/river-engineering-map.html`. `--offline` embeds the viewer assets in the HTML; `--no-open` prevents the CLI from opening a browser. The resulting HTML can be viewed without a server or network connection. Keep the Markdown as the editable source and regenerate the HTML after changes.

To explicitly open the generated file on Windows:

```powershell
Invoke-Item docs/river-engineering-map.html
```

The initial dependency installation requires access to the npm registry. Subsequent HTML generation uses the local installation.

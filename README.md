# Summer Ghost

A Japanese monospace font for Ghostty.
It combines Ubuntu Mono Latin glyphs with a compatible, familiar Japanese layer and deterministic terminal geometry.

- [Ubuntu Mono](https://design.ubuntu.com/font) supplies Latin and the base for modifier symbols.
- [M PLUS 1p](https://fonts.google.com/specimen/M+PLUS+1p) Regular/Bold supply the primary Japanese glyph selection and are fetched from a pinned Google Fonts revision for reproducible builds.
- [NINJAL Hentaigana](https://cid.ninjal.ac.jp/kana/font/) supplies its dedicated 288-codepoint layer directly from the official distribution.
- [BIZ UDGothic](https://github.com/googlefonts/morisawa-biz-ud-gothic) supplies broad Japanese fallback coverage, kanji, and the variation-sequence layer.
- [IBM Plex Sans JP](https://github.com/IBM/plex/tree/master/packages/plex-sans-jp) remains the fallback for uncovered non-private-use characters.
- Historical terminal arrow contours (U+2190..U+2193, U+21B5, U+23CE, U+21D0, U+21D2) are embedded locally from the last-good bits with no external build dependency; U+2190/U+2192 receive a local terminal-icon centerline alignment. U+2731, other check marks, modifiers, box/block drawing, and semantic geometry remain deterministic local constructions.
  Enclosed digits retain IBM Plex Sans JP outlines and receive a local cell fit.

![](specimen.png)

### Metrics and rendering

- UPM 1024 with 512-unit half-width and 1024-unit full-width cells.
- Ascent 850, descent 174, line gap 0, and fixed-pitch advances.
- Four styles: Regular, Bold, Italic, and Bold Italic.
- The Japanese layer and terminal symbols are fitted for stable one-cell and two-cell rendering.
  Ghostty may still apply contextual fitting to symbol-like characters, so apparent size can vary with neighboring cells or IME state.
- The specimen shows source roles and generated geometry without asserting exact visual identity.

## Installation

[uv](https://docs.astral.sh/uv/) is required.
Build and validate the four styles with:

```console
$ make build check
```

Install after review with:

```console
$ make install
```

Configure Ghostty to use the family:

```ini
font-family = Summer Ghost
```

Ghostty can use its own terminal sprites by default.
To request the font's box/block outlines explicitly:

```ini
font-codepoint-map = U+2500-U+259F=Summer Ghost
```

Run `make help` for available targets and installation-directory overrides.

## License

Summer Ghost contains font software covered by the Ubuntu Font Licence 1.0, the SIL Open Font License 1.1, and Apache License 2.0.
See [THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES.md) for attribution and license details.

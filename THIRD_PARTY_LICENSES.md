# Third-Party Licenses

Summer Ghost is built locally from, or contains outlines derived from, the font software listed below. Copyright and license terms remain with their respective owners. This notice is informational and does not replace the license files distributed by each upstream project.

## Ubuntu Mono 0.83

- Source: https://design.ubuntu.com/font
- Archive: https://assets.ubuntu.com/v1/0cef8205-ubuntu-font-family-0.83.zip
- License: Ubuntu Font Licence 1.0 (`LICENCE.txt` in the archive)
- Copyright: Canonical Ltd. and Dalton Maag

## Circle M+ 1m 2020-04-15

- Source: https://itouhiro.github.io/mixfont-mplus-ipa/mplus/
- Archive: https://github.com/itouhiro/mixfont-mplus-ipa/releases/download/v2020.0415/circle-mplus-1m-20200415.7z
- Inclusion path: Adjusted glyphs imported through the pinned Cyroit binaries
- License: See `LICENSE_E` and `LICENSE_J` in the upstream archive
- Copyright: M+ FONTS PROJECT and itouhiro

## Cyroit (from Ubroit v1.8.0)

- Source: https://github.com/omonomo/Ubroit/tree/v1.8.0
- Files used: `sourceFonts/Cyroit.nopatch/Cyroit-Regular.nopatch.ttf` and `Cyroit-Bold.nopatch.ttf`
- Embedded Cyroit version: 3.11.0, as reported by the binaries' name tables
- Purpose: Adjusted Circle M+ and BIZ UDGothic Japanese glyphs
- Binary font license: SIL Open Font License 1.1
- Upstream build-script license: MIT License
- Copyright: omonomo and the respective source-font authors

The Cyroit name-table notice additionally credits the Inconsolata Project Authors, the National Institute for Japanese Language and Linguistics for NINJAL Hentaigana, and Ryan McIntyre for Symbols Nerd Font. Summer Ghost imports only selected Japanese mappings from Cyroit and rejects all private-use mappings; it does not intentionally import Inconsolata Latin glyphs or Nerd Fonts icons.

## BIZ UDGothic 1.051

- Source: https://github.com/googlefonts/morisawa-biz-ud-gothic
- Archive: https://github.com/googlefonts/morisawa-biz-ud-gothic/releases/download/v1.051/BIZUDGothic.zip
- License: SIL Open Font License 1.1
- Copyright: The BIZ UDGothic Project Authors and Morisawa Inc.

## IBM Plex Sans JP 1.003

- Source: https://github.com/IBM/plex
- Release: `@ibm/plex-sans-jp@2.0.0`
- Pinned commit: `ceee82fa88781b8310b198fd302480efaeac609e`
- License: SIL Open Font License 1.1; reserved font name: `Plex`
- Copyright: IBM Corp.

Summer Ghost does not use any upstream reserved font name as its family name. The generated font intentionally excludes private-use glyphs, including Nerd Fonts glyphs.

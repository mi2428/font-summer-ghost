# Third-Party Licenses

Summer Ghost is assembled from the approved sources below and from locally generated semantic geometry plus historical terminal outlines embedded locally.
Copyright and license terms remain with the respective owners.
This notice supplements, and does not replace, the license files shipped by each source.

## Ubuntu Mono 0.83

- Source: [Ubuntu Font](https://design.ubuntu.com/font)
- Archive: `https://assets.ubuntu.com/v1/0cef8205-ubuntu-font-family-0.83.zip`
- Archive SHA-256: `61a2b342526fd552f19fef438bb9211a8212de19ad96e32a1209c039f1d68ecf`
- License: Ubuntu Font Licence 1.0 (`LICENCE.txt` and `LICENCE-FAQ.txt`)
- Copyright: Canonical Ltd. and Dalton Maag

## M PLUS 1p

- Distribution: [Google Fonts `ofl/mplus1p`](https://github.com/google/fonts/tree/2796410152d4f9524b68ed46e69c1b60f8e0f7c3/ofl/mplus1p)
- Pinned commit: `2796410152d4f9524b68ed46e69c1b60f8e0f7c3`
- Regular file: `https://raw.githubusercontent.com/google/fonts/2796410152d4f9524b68ed46e69c1b60f8e0f7c3/ofl/mplus1p/MPLUS1p-Regular.ttf`
- Regular SHA-256: `2f294ad496432b1608f070d310e3aa2adcf1de4af429f4901df97ec4bd361ed1`
- Bold file: `https://raw.githubusercontent.com/google/fonts/2796410152d4f9524b68ed46e69c1b60f8e0f7c3/ofl/mplus1p/MPLUS1p-Bold.ttf`
- Bold SHA-256: `76eb077b0a31ca33ca40238e47da5a17e2786741607cec09678d7d2e5ab1afc1`
- License: SIL Open Font License 1.1 (`ofl/mplus1p/OFL.txt`)
- Copyright: M+ FONTS PROJECT and contributors

## BIZ UDGothic 1.051

- Source: [Google Fonts BIZ UDGothic](https://github.com/googlefonts/morisawa-biz-ud-gothic)
- Archive: `https://github.com/googlefonts/morisawa-biz-ud-gothic/releases/download/v1.051/BIZUDGothic.zip`
- Archive SHA-256: `30692df621b92df13b88f1360aed1ab6ae50de441bce751a396c6439045cd759`
- License: SIL Open Font License 1.1 (`OFL.txt`)
- Copyright: The BIZ UDGothic Project Authors and Morisawa Inc.

## NINJAL Hentaigana 1.01

- Source: [National Institute for Japanese Language and Linguistics](https://cid.ninjal.ac.jp/kana/font/)
- Archive: `https://cid.ninjal.ac.jp/kana/ninjal_hentaigana.zip`
- Archive SHA-256: `62b01c19cb40dc4b64b1e1da776fca483e19e21c2772cc3f9db9a067bedbc84d`
- Build file: `ninjal_hentaigana.ttf`
- TTF SHA-256: `e1301406c49dffed801bc12f0bb6a148f90215d4cf7d3a7bb0831cd798f6345e`
- License: Apache License 2.0 (the official archive's readme and license notice)
- Copyright: National Institute for Japanese Language and Linguistics (NINJAL), 2018

## IBM Plex Sans JP 3.0.0

- Source: [IBM Plex](https://github.com/IBM/plex/tree/master/packages/plex-sans-jp)
- Release: [`@ibm/plex-sans-jp@3.0.0`](https://github.com/IBM/plex/releases/tag/%40ibm/plex-sans-jp%403.0.0); internal font version 1.004
- Pinned commit: `89cba80dad75561262e758f4b6ddd474c5119796`
- Regular file: `https://raw.githubusercontent.com/IBM/plex/89cba80dad75561262e758f4b6ddd474c5119796/packages/plex-sans-jp/fonts/complete/ttf/unhinted/IBMPlexSansJP-Regular.ttf`
- Regular SHA-256: `0168493ae143d16e4c0d374c090b1ee5eab9ee475536d2e429368dbcfc4a6abe`
- Bold file: `https://raw.githubusercontent.com/IBM/plex/89cba80dad75561262e758f4b6ddd474c5119796/packages/plex-sans-jp/fonts/complete/ttf/unhinted/IBMPlexSansJP-Bold.ttf`
- Bold SHA-256: `070c08915b21a9484e31a73594e4aae69991e4477959a96a6ab4031f4e30ec9f`
- License: SIL Open Font License 1.1; reserved font name `Plex`
- Copyright: IBM Corp.
- Enclosed digits use IBM Plex Sans JP outlines and are locally fitted to the Summer Ghost half-width cell.

## Nerd Fonts Symbols 3.4.0 (selected glyphs only)

- Source: [Nerd Fonts Symbols Only](https://github.com/ryanoasis/nerd-fonts/tree/fa7b859994228a9c8759f99c55a8d31ee92a1b5e/patched-fonts/NerdFontsSymbolsOnly)
- Pinned commit: `fa7b859994228a9c8759f99c55a8d31ee92a1b5e`
- File: `SymbolsNerdFont-Regular.ttf` (the same bytes as Ghostty 1.4.0's bundled Symbols Nerd Font)
- SHA-256: `71db104aa66567d0efe0b98758f9dfc1895573a453fe85fb53d1c38544a55106`
- Selected codepoints: U+E235, U+F126, U+F0079, U+F007D, U+F0083, U+F0084, U+F008E, U+F011B, U+F013C, U+F013F, U+F0140, U+F0143, U+F015A, U+F0E0F.
- Symbols-only assembly: MIT License, copyright Ryan L McIntyre, 2014.
- Font Awesome U+F126: SIL Open Font License 1.1 for font outlines, copyright Fonticons, Inc., 2022; reserved font name `Font Awesome`. The SVG/JS CC BY terms do not apply to these copied font outlines.
- Font Awesome Extension U+E235: MIT License, copyright André Luiz Gava, 2017. The original notice is pinned to [commit 09d80249058ee8018a45da30add4339289dbb466](https://github.com/AndreLGava/font-awesome-extension/blob/09d80249058ee8018a45da30add4339289dbb466/LICENCE).
- Material Design icons (the selected U+F0000-range characters): Apache License 2.0, Pictogrammers contributors.
- Outlines are decomposed and proportionally fitted into a 512-unit cell while retaining the donor aspect ratios. No other Nerd Fonts glyphs are imported.

The build downloads and verifies each upstream notice, including the complete Apache 2.0 text, and bundles them in `dist/THIRD_PARTY_LICENSES.txt`.

## DejaVu 2.37 (selected glyphs only)

- Source: [DejaVu Fonts](https://dejavu-fonts.github.io/)
- Archive: `https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip`
- Archive SHA-256: `7576310b219e04159d35ff61dd4a4ec4cdba4f35c00e002a136f00e96a908b0a`
- DejaVu Sans Mono Regular supplies U+21D5, U+21E1, U+21E3, U+237D, U+2718, and U+2726. Baselines and proportions are preserved, using a scale of 532/1120 to match the primary face's x-height instead of fitting each glyph's ink independently.
- Copyright: Bitstream, Inc., 2003; DejaVu changes are public domain. The archive also includes the Arev notices, copyright Tavmjong Bah, 2006.
- License: the archive's `LICENSE` (Bitstream Vera/DejaVu and applicable Arev terms), reproduced in `dist/THIRD_PARTY_LICENSES.txt`.
- Summer Ghost is not distributed under any reserved upstream name.

## JetBrains Mono Regular (selected glyphs only)

- Pinned commit: `19371302b95d218af43299bce79ddbddd0bc364d`
- Source: `https://raw.githubusercontent.com/JetBrains/JetBrainsMono/19371302b95d218af43299bce79ddbddd0bc364d/fonts/ttf/JetBrainsMono-Regular.ttf`
- SHA-256: `e6fd0d7e91550b3ed2b735d4312474362c4716edc4fc0577a0f61ed782d5aed1`
- Font version: 2.305; this matches the installed JetBrains Mono used by the measured macOS fallback.
- Selected codepoints: U+276E, U+276F, U+27E8, U+27E9, scaled by 532/550 with their original bearings and baseline.
- Copyright: The JetBrains Mono Project Authors, 2020.
- License: SIL Open Font License 1.1; the pinned `OFL.txt` is bundled in `dist/THIRD_PARTY_LICENSES.txt`.

## Locally generated geometry

The historical terminal outlines U+2190..U+2193, U+21B5, U+23CE, U+21D0, and U+21D2 are embedded locally from verified last-good bits and have no external build dependency. U+2713/U+2714, modifiers, box drawing, Block Elements, white parentheses, and uncovered semantic symbols are generated from Unicode meaning and the fixed Summer Ghost cell metrics.
Braille U+2800–U+28FF is generated from a fixed eight-square-dot grid. Rounded caps U+E0B4/U+E0B6 are mirrored local cubic arcs converted to TrueType quadratics, with optical curvature compensation. No Menlo outlines are copied; its previous rendered placement is only a comparison reference.

Summer Ghost does not use an upstream reserved font name as its family name. Private-use characters are restricted to the 14 Nerd Fonts icons and two locally generated caps above; all other private-use mappings are rejected by validation.

# AFAC parser fixtures

Frozen, byte-identical copies of two official AFAC annual workbooks are kept here so
the parser is tested against both Excel generations without network access.

| Fixture | Official period | Format family | SHA-256 |
|---|---:|---|---|
| `afac_1992_legacy.xls` | 1992 | legacy BIFF `.xls` wide blocks | `cdd82ce21a8a420514497741b0c5a923f7931fc6afc9f25714e075557f864954` |
| `afac_2015_modern.xlsx` | 2015 | OOXML `.xlsx` wide + operational sheets | `26deefd5c33661215a48bc6f9c41701b28ed410d6a036676ca960b117815eeb8` |

The files are used only as immutable test inputs. Their source URLs and acquisition
metadata remain in the bronze manifest.

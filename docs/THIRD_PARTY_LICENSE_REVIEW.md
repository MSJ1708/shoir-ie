# Third-Party Software and Asset Licence Review

**Assessment date:** October 21, 2026  
**Status:** **Incomplete — do not describe the software supply chain as fully cleared.**

Shoir-IE's root LICENSE states that the repository's own code is proprietary and reserves rights to the named copyright holder. That notice does **not** replace, override or satisfy licence obligations for separately licensed code, transitive dependencies, bundled assets, icons, fonts, datasets, screenshots or other third-party materials.

## Direct packages declared in requirements.txt

The current declaration includes:

- streamlit
- pulp[cbc]==3.3.2
- folium
- streamlit-folium
- pandas
- numpy
- plotly
- Pillow
- scipy
- openpyxl
- xlsxwriter
- reportlab
- python-pptx
- scikit-learn
- requests
- kaleido>=1.0.0
- playwright
- pytest>=9.0.3,<10
- psycopg2-binary>=2.9,<3
- paho-mqtt>=2,<3
- duckdb>=1.0,<2
- xlrd>=2.0.1,<3
- pypdf==6.21.2 (used by artifact-level PDF export tests; BSD-3-Clause)

This is a source-level list of direct requirements, not a complete licence audit. Transitive dependencies, optional extras, solver binaries, JavaScript/TypeScript imports, fonts, images and other assets need to be inventoried separately. Their exact resolved versions can differ between environments.

## Required before a paid production launch

1. Resolve and pin the installed Python and JavaScript/TypeScript dependency graph for the deployed build.
2. Generate an SPDX or CycloneDX Software Bill of Materials (SBOM) and machine-readable licence report from that exact build.
3. Review each direct and transitive package licence for distribution, hosted use, modification, attribution, source-disclosure and notice obligations.
4. Preserve third-party licence/copyright notices wherever required. Review the solver/runtime components pulled by optional dependencies such as pulp[cbc].
5. Build an asset inventory for app icons, fonts, logos, images, illustrations, charts, datasets, documentation, sample workbooks and copied or generated content. Record source, ownership, licence and permission evidence.
6. Verify that AI outputs, user uploads or externally sourced material used in examples, benchmark reports or marketing collateral are not represented as owned third-party content without appropriate rights.
7. Scan repository history and current files for copied proprietary material, accidentally committed secrets and assets with unclear provenance; remove or rotate any exposed secrets as required.
8. Keep a notice bundle and SBOM with each release, and repeat this review after material dependency or asset changes.

## Copyright and branding

The Saudi Authority for Intellectual Property (SAIP) provides an optional registration service for computer software and applications. Registration may help document authorship, but it does not cure copied code or third-party licence violations. Keep dated source/version records, contribution or contractor assignments and proof of asset permissions. Check the Shoir-IE name, logo and relevant marks for conflicts before broad commercial use.

Official reference: [SAIP software and application copyright registration](https://www.saip.gov.sa/en/services/copyrights/copyr1).

# Product shell boundary

Shoir-IE remains a browser-first Streamlit application. The new Industrial Workbook surface uses responsive CSS and compact controls so the core workflow remains usable on smaller screens.

## Current support

- Responsive browser workspace
- Excel-compatible .xlsx import/export
- Keyboard-oriented cell editing through the browser grid
- Persistent saved workbooks per Shoir-IE workspace

## Packaging path

Desktop packaging can wrap the hosted web application in an enterprise browser shell. Mobile can use the responsive web surface or a managed web-app wrapper.

A native desktop/mobile codebase is intentionally not duplicated inside this repository; the engineering and persistence services remain shared behind the existing application.

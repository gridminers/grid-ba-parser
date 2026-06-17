# grid-ba-parser

Parser for unstructured PDF documents that are not OCR-readable. The parser renders PDF pages as images, reads each page with a vision-language model (VLM), applies rule-based key-value extraction, and exports to CSV or SQLite.

## How it works

1. Convert PDF pages to images (`pdf_to_images`)
2. Send page images to a vision model client (`VisionModelClient.extract`)
3. Normalize VLM output into structured key-value pairs (`RuleBasedFormatter`)
4. Export structured output to CSV (`export_to_csv`) and/or SQLite (`export_to_sqlite`)

## CLI usage

```bash
python -m grid_ba_parser --pdf invoice.pdf --vision-json vlm_output.json --csv output.csv --sqlite output.db --dpi 200
```

`--vision-json` is a deterministic adapter input where keys are page numbers and values are raw extracted text from the vision model.


Relative and absolute file paths are both supported.

import argparse
from pathlib import Path

from app.batch import export_mock_db_payload, parse_and_optionally_export, register_folder_pdfs
from app.config import get_settings
from app.storage import LocalStore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan a folder for PDFs, parse them, and write mock DB export JSON files."
    )
    parser.add_argument("--folder", required=True, help="Folder containing PDFs to scan")
    parser.add_argument("--recursive", action="store_true", help="Scan subfolders")
    parser.add_argument("--vlm-provider", default=None, help="Override VLM provider")
    parser.add_argument("--vlm-model", default=None, help="Override VLM model")
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Do not parse; only export already parsed drafts for discovered documents",
    )
    parser.add_argument(
        "--rescan-existing",
        action="store_true",
        help="Reprocess PDFs even if a mock DB export JSON already exists",
    )
    args = parser.parse_args()

    settings = get_settings()
    store = LocalStore(settings.data_dir)
    records = register_folder_pdfs(
        store=store,
        folder_path=Path(args.folder),
        recursive=args.recursive,
    )
    if not records:
        print("No PDFs found.")
        return 0

    for record in records:
        export_path = store.mock_db_exports_dir() / f"{record.id}.json"
        if export_path.exists() and not args.rescan_existing:
            print(f"Skipping {record.filename}; export already exists at {export_path}")
            continue
        print(f"Processing {record.filename} ({record.id})")
        if args.export_only:
            result = export_mock_db_payload(store=store, document_id=record.id)
        else:
            result = parse_and_optionally_export(
                store=store,
                settings=settings,
                document_id=record.id,
                vlm_provider=args.vlm_provider,
                vlm_model=args.vlm_model,
                export_after_parse=True,
            )
        if result:
            print(f"  {result.status}: {result.fields} field(s) -> {result.export_path or 'n/a'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

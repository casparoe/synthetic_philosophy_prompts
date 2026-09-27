#!/usr/bin/env python
"""Upload the staging folder written by tools/export_hf.py to a Hugging Face dataset repo.

    python tools/upload_hf.py --repo casparoe/synthetic_philosophy_prompts --folder hf_export
    python tools/upload_hf.py --repo ... --folder ... --public      # flip an existing repo to public

The token is read from a file (default api_keys/huggingface_write.txt, which is
git-ignored) and handed to the library in memory: it is never printed, never put on
a command line, and never written into the uploaded folder. The repo is created
private unless --public is given. upload_folder makes one commit with every file
of the folder that is new or changed (large files are pre-uploaded as LFS/Xet
objects, so an interrupted upload can simply be run again). Only the staging folder
is uploaded, never the repository root, so the api_keys folder cannot travel along;
an ignore pattern for it is added anyway.
"""

import argparse
import sys
from pathlib import Path

from huggingface_hub import HfApi

IGNORE = ["api_keys/*", "**/api_keys/*", "**/.DS_Store", "*.tmp", "**/*.tmp", ".cache/*", "**/.cache/*"]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True, help="dataset repo id, e.g. casparoe/synthetic_philosophy_prompts")
    parser.add_argument("--folder", default="hf_export")
    parser.add_argument("--token-file", default="api_keys/huggingface_write.txt")
    parser.add_argument("--public", action="store_true", help="make the repo public (default: private)")
    parser.add_argument("--no-upload", action="store_true", help="only create the repo / change its visibility")
    parser.add_argument("--message", default="Update dataset shards and card")
    args = parser.parse_args()

    token = Path(args.token_file).read_text().strip()
    api = HfApi(token=token)
    me = api.whoami()["name"]
    url = api.create_repo(args.repo, repo_type="dataset", private=not args.public, exist_ok=True)
    print(f"authenticated as {me}; repo {url}")
    if args.public:
        api.update_repo_settings(args.repo, repo_type="dataset", private=False)
        print("visibility: public")
    if args.no_upload:
        return
    folder = Path(args.folder)
    if not folder.is_dir():
        sys.exit(f"{folder} is not a directory")
    if (folder / "api_keys").exists():
        sys.exit("refusing to upload: the staging folder contains an api_keys directory")
    api.upload_folder(
        repo_id=args.repo,
        repo_type="dataset",
        folder_path=str(folder),
        ignore_patterns=IGNORE,
        commit_message=args.message,
    )
    files = api.list_repo_files(args.repo, repo_type="dataset")
    print(f"upload finished: {len(files)} files in {args.repo}")


if __name__ == "__main__":
    main()

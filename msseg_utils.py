import os
import glob
import zipfile
import random
from pathlib import Path

def unzip_if_needed(zip_path, extract_dir):
    """Extract a zip once and return the extracted directory."""
    if zip_path and os.path.exists(zip_path):
        marker = Path(extract_dir) / ".extracted"
        if not marker.exists():
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            marker.touch()
        return extract_dir
    return extract_dir

def first_match(files, include_terms, exclude_terms=()):
    """Pick the first file containing all include_terms and none of exclude_terms."""
    include_terms = [t.upper() for t in include_terms]
    exclude_terms = [t.upper() for t in exclude_terms]
    candidates = []
    for f in files:
        name = os.path.basename(f).upper()
        if all(t in name for t in include_terms) and not any(t in name for t in exclude_terms):
            candidates.append(f)
    return sorted(candidates)[0] if candidates else None

def find_case_files(case_dir):
    """Find FLAIR, T1, T2, and lesion mask inside one subject/case folder."""
    nii_files = glob.glob(os.path.join(case_dir, "**", "*.nii*"), recursive=True)
    if not nii_files:
        return None

    flair = first_match(nii_files, ["FLAIR"])
    t2 = first_match(nii_files, ["T2"], exclude_terms=["T2STAR", "T2_STAR"])
    t1 = first_match(nii_files, ["T1"], exclude_terms=["GADO", "GD", "GAD", "CE", "CONTRAST"])

    # Common label names across MSSEG/MSLesSeg variants.
    label = (
        first_match(nii_files, ["CONSENSUS"])
        or first_match(nii_files, ["LESION"])
        or first_match(nii_files, ["MASK"])
        or first_match(nii_files, ["SEG"])
        or first_match(nii_files, ["GT"])
    )

    # Avoid accidentally selecting an image as a label if names are ambiguous.
    image_set = {p for p in [flair, t1, t2] if p}
    if label in image_set:
        label = None

    if flair and t1 and t2 and label:
        return {"flair": flair, "t1": t1, "t2": t2, "label": label}
    return None

def collect_dataset(root_dir, source_name):
    """Recursively collect valid cases with all 3 modalities and a label."""
    root_dir = str(root_dir)
    if not os.path.exists(root_dir):
        print(f"WARNING: {source_name} root not found: {root_dir}")
        return []

    all_dirs = [root_dir] + [p for p, _, _ in os.walk(root_dir)]
    cases = []
    seen = set()
    for d in all_dirs:
        item = find_case_files(d)
        if item is None:
            continue
        key = tuple(item[k] for k in ["flair", "t1", "t2", "label"])
        if key in seen:
            continue
        seen.add(key)
        item["source"] = source_name
        item["case_id"] = f"{source_name}_{len(cases):03d}"
        cases.append(item)
    return cases

def stratified_split(files, val_fraction=0.2, seed=42):
    """Keep both datasets represented in train and validation."""
    rng = random.Random(seed)
    train, val = [], []
    for source in sorted({f["source"] for f in files}):
        group = [f for f in files if f["source"] == source]
        rng.shuffle(group)
        n_val = max(1, int(round(len(group) * val_fraction))) if len(group) > 1 else 0
        val.extend(group[:n_val])
        train.extend(group[n_val:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val

def binarize_label(x):
    """Labels must be binary: background=0, lesion=1."""
    return (x > 0).astype(x.dtype)

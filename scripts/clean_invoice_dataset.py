import csv
from pathlib import Path


SOURCE_FILE = Path("source_data/invoices_merged_clean.csv")
OUTPUT_FILE = Path("seed_data/invoices_merged_clean.csv")


def to_int(value):
    return int(float(value or 0))


def to_float(value):
    return float(value or 0)


def recompute_discount_eligible(row):
    is_open = row["invoice_status"].strip().lower() == "open"
    enough_days = to_int(row["days_until_due"]) >= 10
    not_disputed = to_int(row["disputed"]) == 0
    minimum_amount = to_float(row["invoice_amount_display"]) >= 50000

    return int(
        is_open
        and enough_days
        and not_disputed
        and minimum_amount
    )


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with SOURCE_FILE.open("r", newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)

        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError("Input CSV has no header.")

        rows = list(reader)

    old_count = sum(
        to_int(row["discount_eligible_flag"]) == 1
        for row in rows
    )

    new_count = 0
    mismatches = 0

    for row in rows:
        old_flag = to_int(row["discount_eligible_flag"])
        new_flag = recompute_discount_eligible(row)

        row["discount_eligible_flag"] = str(new_flag)

        new_count += new_flag
        mismatches += old_flag != new_flag

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Total invoices: {len(rows)}")
    print(f"Old eligible count: {old_count}")
    print(f"New eligible count: {new_count}")
    print(f"Flag mismatches: {mismatches}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
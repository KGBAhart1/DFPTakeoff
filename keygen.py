"""
DFP TakeoffPro — License Key Generator
---------------------------------------
Run this script on YOUR machine to generate license keys for customers.
Never distribute this file.

Usage:
    python keygen.py
"""

from license import generate_key, validate_key
from datetime import date, timedelta


def main():
    print("=" * 55)
    print("  DFP TakeoffPro  —  License Key Generator")
    print("=" * 55)
    print()

    # Customer info (optional, for your records only)
    customer = input("Customer name / company (for your records): ").strip()

    # Expiry
    print("\nExpiry options:")
    print("  1. 1 year from today")
    print("  2. 2 years from today")
    print("  3. Lifetime (expires 2099)")
    print("  4. Custom date")
    choice = input("Choice [1]: ").strip() or "1"

    today = date.today()
    if choice == "1":
        expiry = today.replace(year=today.year + 1)
    elif choice == "2":
        expiry = today.replace(year=today.year + 2)
    elif choice == "3":
        expiry = date(2099, 12, 31)
    else:
        ds = input("Enter expiry date (YYYY-MM-DD): ").strip()
        expiry = date.fromisoformat(ds)

    # Seats
    seats_str = input("Number of seats [1]: ").strip() or "1"
    seats = int(seats_str)

    # Generate
    key = generate_key(expiry, seats)
    ok, msg, _, _ = validate_key(key)

    print()
    print("=" * 55)
    print(f"  Customer : {customer}")
    print(f"  Expiry   : {expiry}")
    print(f"  Seats    : {seats}")
    print(f"  Status   : {msg}")
    print()
    print(f"  LICENSE KEY:")
    print(f"  {key}")
    print("=" * 55)

    # Save to a log file
    log_path = "keys_issued.txt"
    with open(log_path, "a") as f:
        f.write(
            f"{date.today()}  |  {customer}  |  expires {expiry}  "
            f"|  seats {seats}  |  {key}\n"
        )
    print(f"\nKey logged to {log_path}")
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()

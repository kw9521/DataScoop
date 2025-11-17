#!/usr/bin/env python3
"""
Scoops & Smiles – Inventory & Income Statement App

• Python 3.x, Tkinter (built‑in), sqlite3 (built‑in)
• Data is persisted to a local SQLite file (scoops.db) and CSV import/export is supported
• GAAP‑style Monthly Income Statement per location and company‑wide

Folder layout (create alongside this file):
.
├── DataScoop.py            # this file
├── scoops.db               # auto‑created on first run
├── data/                   # CSV import/export directory (auto‑created) - populated when you export data from the app
│   ├── purchases.csv
│   ├── sales.csv
│   └── locations.csv
└── README.md              

Notes
-----
- This app uses a weighted‑average cost per ounce for COGS and inventory valuation.
- Inventory is tracked in ounces (1 container = 5 gallons = 640 ounces).
- Napkins: $20 per 10,000, 2 per order → $0.004 per order.
- Cones/dishes: variable cost per order by container type.
- Sale price is determined by size (Kiddie/Small/Medium/Large) and is identical for cone/dish types per brief.
- You can add locations, record purchases, record sales, import/export CSVs, and generate monthly reports.

Team Config
-----------
- The app stores the DB path in `config.json` (created on first run). By default, it points to `scoops.db` in the project folder.
- Everyone should keep the repo structure the same so paths are consistent.

Sign In Function for managers:
-----------------
Username: manager
Password: password

"""
import csv
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

APP_TITLE = "Scoops & Smiles – Inventory & Reporting"
DB_DEFAULT = "scoops.db"
CONFIG_PATH = "config.json"
DATA_DIR = Path("data")

# ---------- Business Constants ----------
OZ_PER_CONTAINER = 5 * 128  # 640 oz
NAPKIN_COST_PER_ORDER = 20.0 / 10000.0 * 2  # $20 per 10,000; 2 per order

SALE_PRICES = {
    "Kiddie": 3.00,
    "Small": 3.50,
    "Medium": 4.00,
    "Large": 4.50,
}

SCOOPS_OZ = {
    "Kiddie": 4,
    "Small": 8,
    "Medium": 12,
    "Large": 16,
}

FIXED_EXPENSES = {
    "rent": 1000.0,
    "utilities": 250.0,
    "labor": 15000.0,
    "equipment_lease": 2000.0,
}

FLAVORS = [
    ("Vanilla", 2.0),
    ("Chocolate", 2.0),
    ("Neapolitan", 2.5),
    ("Cookies & Cream", 3.0),
    ("Cookie Dough", 3.0),
]

CONTAINERS = [
    ("Standard Cone", 5.00, 100),
    ("Waffle Cone", 6.00, 100),
    ("Dish w/ Spoon", 4.50, 100),
]

################## Setup / DB ##################

def ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    cfg = {"db_path": DB_DEFAULT}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return cfg


def get_conn():
    cfg = load_config()
    return sqlite3.connect(cfg["db_path"])  # path relative to repo


def init_db():
    with get_conn() as con:
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS flavors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                cost_per_container REAL NOT NULL
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS containers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                price_per_pack REAL NOT NULL,
                units_per_pack INTEGER NOT NULL
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory_state (
                location_id INTEGER NOT NULL,
                flavor_id INTEGER NOT NULL,
                ounces_on_hand REAL NOT NULL DEFAULT 0,
                avg_cost_per_oz REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (location_id, flavor_id),
                FOREIGN KEY (location_id) REFERENCES locations(id),
                FOREIGN KEY (flavor_id) REFERENCES flavors(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id INTEGER NOT NULL,
                flavor_id INTEGER NOT NULL,
                purchase_date TEXT NOT NULL,
                containers INTEGER NOT NULL,
                cost_per_container REAL NOT NULL,
                FOREIGN KEY (location_id) REFERENCES locations(id),
                FOREIGN KEY (flavor_id) REFERENCES flavors(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id INTEGER NOT NULL,
                flavor_id INTEGER NOT NULL,
                sale_date TEXT NOT NULL,
                size TEXT NOT NULL,
                container_type_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                FOREIGN KEY (location_id) REFERENCES locations(id),
                FOREIGN KEY (flavor_id) REFERENCES flavors(id),
                FOREIGN KEY (container_type_id) REFERENCES containers(id)
            );
            """
        )
        cur.execute("SELECT COUNT(*) FROM flavors")
        if cur.fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO flavors(name, cost_per_container) VALUES (?, ?)", FLAVORS
            )
        cur.execute("SELECT COUNT(*) FROM containers")
        if cur.fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO containers(name, price_per_pack, units_per_pack) VALUES (?,?,?)",
                CONTAINERS,
            )
        con.commit()

################### Data helpers ###################

def list_locations(con):
    cur = con.cursor()
    cur.execute("SELECT id, name FROM locations ORDER BY name")
    return cur.fetchall()


def list_flavors(con):
    cur = con.cursor()
    cur.execute("SELECT id, name FROM flavors ORDER BY name")
    return cur.fetchall()


def list_containers(con):
    cur = con.cursor()
    cur.execute("SELECT id, name, price_per_pack, units_per_pack FROM containers ORDER BY id")
    return cur.fetchall()


def add_location(name):
    with get_conn() as con:
        cur = con.cursor()
        try:
            cur.execute("INSERT INTO locations(name) VALUES (?)", (name.strip(),))
            con.commit()
            cur.execute("SELECT id FROM locations WHERE name=?", (name.strip(),))
            loc_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM flavors")
            for (flavor_id,) in cur.fetchall():
                cur.execute(
                    "INSERT OR IGNORE INTO inventory_state(location_id, flavor_id, ounces_on_hand, avg_cost_per_oz) VALUES (?,?,0,0)",
                    (loc_id, flavor_id),
                )
            con.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def record_purchase(location_id, flavor_id, containers, purchase_date=None):
    if purchase_date is None:
        purchase_date = datetime.now().strftime("%Y-%m-%d")
    with get_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT cost_per_container FROM flavors WHERE id=?", (flavor_id,))
        cost_per_container = float(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO purchases(location_id, flavor_id, purchase_date, containers, cost_per_container)
            VALUES (?,?,?,?,?)
            """,
            (location_id, flavor_id, purchase_date, containers, cost_per_container),
        )
        added_oz = containers * OZ_PER_CONTAINER
        added_cost = containers * cost_per_container
        cur.execute(
            "SELECT ounces_on_hand, avg_cost_per_oz FROM inventory_state WHERE location_id=? AND flavor_id=?",
            (location_id, flavor_id),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO inventory_state(location_id, flavor_id, ounces_on_hand, avg_cost_per_oz) VALUES (?,?,?,?)",
                (location_id, flavor_id, 0, 0),
            )
            old_oz, old_avg = 0.0, 0.0
        else:
            old_oz, old_avg = float(row[0]), float(row[1])
        old_cost = old_oz * old_avg
        new_oz = old_oz + added_oz
        new_avg = (old_cost + added_cost) / new_oz if new_oz > 0 else 0.0
        cur.execute(
            "UPDATE inventory_state SET ounces_on_hand=?, avg_cost_per_oz=? WHERE location_id=? AND flavor_id=?",
            (new_oz, new_avg, location_id, flavor_id),
        )
        con.commit()


def record_sale(location_id, flavor_id, size, container_type_id, quantity, sale_date=None):
    if sale_date is None:
        sale_date = datetime.now().strftime("%Y-%m-%d")
    if size not in SCOOPS_OZ:
        raise ValueError("Invalid size")
    oz_needed = SCOOPS_OZ[size] * quantity
    with get_conn() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT ounces_on_hand FROM inventory_state WHERE location_id=? AND flavor_id=?",
            (location_id, flavor_id),
        )
        row = cur.fetchone()
        on_hand = float(row[0]) if row else 0.0
        if on_hand < oz_needed:
            raise ValueError("Insufficient inventory for this sale.")
        cur.execute(
            """
            INSERT INTO sales(location_id, flavor_id, sale_date, size, container_type_id, quantity)
            VALUES (?,?,?,?,?,?)
            """,
            (location_id, flavor_id, sale_date, size, container_type_id, quantity),
        )
        new_on_hand = on_hand - oz_needed
        cur.execute(
            "UPDATE inventory_state SET ounces_on_hand=? WHERE location_id=? AND flavor_id=?",
            (new_on_hand, location_id, flavor_id),
        )
        con.commit()


def _month_bounds(year: int, month: int):
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year+1:04d}-01-01" if month == 12 else f"{year:04d}-{month+1:02d}-01"
    return start, end


def generate_income_statement(year: int, month: int):
    start, end = _month_bounds(year, month)
    with get_conn() as con:
        conts = {row[0]: (row[1], float(row[2]), int(row[3])) for row in list_containers(con)}
        statements = []
        company = {k: 0.0 for k in [
            "revenue","cogs_icecream","cogs_containers","cogs_napkins",
            "gross_profit","operating_expenses","operating_income","net_income"]}
        for loc_id, loc_name in list_locations(con):
            cur = con.cursor()
            cur.execute(
                """
                SELECT sale_date, flavor_id, size, container_type_id, quantity
                FROM sales
                WHERE location_id=? AND sale_date>=? AND sale_date<?
                """,
                (loc_id, start, end),
            )
            sales_rows = cur.fetchall()
            revenue = 0.0
            oz_sold_by_flavor = {}
            container_orders = 0
            container_cost = 0.0
            for _date, flavor_id, size, container_type_id, qty in sales_rows:
                revenue += SALE_PRICES.get(size, 0.0) * qty
                oz = SCOOPS_OZ[size] * qty
                oz_sold_by_flavor[flavor_id] = oz_sold_by_flavor.get(flavor_id, 0.0) + oz
                name, price_pack, units = conts[container_type_id]
                container_cost += (price_pack / units) * qty
                container_orders += qty
            icecream_cogs = 0.0
            for flavor_id, oz in oz_sold_by_flavor.items():
                cur.execute(
                    "SELECT avg_cost_per_oz FROM inventory_state WHERE location_id=? AND flavor_id=?",
                    (loc_id, flavor_id),
                )
                row = cur.fetchone()
                avg_cost = float(row[0]) if row and row[0] is not None else 0.0
                icecream_cogs += avg_cost * oz
            napkins_cogs = NAPKIN_COST_PER_ORDER * container_orders
            cogs_total = icecream_cogs + container_cost + napkins_cogs
            gross_profit = revenue - cogs_total
            operating_expenses = sum(FIXED_EXPENSES.values())
            operating_income = gross_profit - operating_expenses
            net_income = operating_income
            st = {
                "revenue": revenue,
                "cogs_icecream": icecream_cogs,
                "cogs_containers": container_cost,
                "cogs_napkins": napkins_cogs,
                "gross_profit": gross_profit,
                "operating_expenses": operating_expenses,
                "operating_income": operating_income,
                "net_income": net_income,
            }
            statements.append((loc_name, st))
            for k in company:
                company[k] += st[k]
        return statements, company


def generate_flavor_sales_report(year: int, month: int):
    start, end = _month_bounds(year, month)
    with get_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM flavors")
        flavor_names = {fid: fname for fid, fname in cur.fetchall()}
        cur.execute("SELECT id, name FROM locations")
        loc_names = {lid: lname for lid, lname in cur.fetchall()}
        cur.execute(
            """
            SELECT location_id, flavor_id, size, SUM(quantity) as qty
            FROM sales
            WHERE sale_date>=? AND sale_date<?
            GROUP BY location_id, flavor_id, size
            ORDER BY location_id, flavor_id
            """,
            (start, end),
        )
        rows = cur.fetchall()
        report = {}
        for loc_id, flavor_id, size, qty in rows:
            key = (loc_id, flavor_id)
            report.setdefault(key, 0)
            report[key] += SCOOPS_OZ[size] * qty
        out = []
        for (loc_id, flavor_id), oz in report.items():
            out.append({
                "Location": loc_names.get(loc_id, f"Loc {loc_id}"),
                "Flavor": flavor_names.get(flavor_id, f"Flavor {flavor_id}"),
                "Ounces Sold": round(oz, 2),
                "Containers (approx)": round(oz / OZ_PER_CONTAINER, 2),
            })
        return out
def generate_inventory_levels():
    """Return inventory on hand per location & flavor with ounce and container approximations."""
    with get_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name FROM locations")
        loc_names = {lid: lname for lid, lname in cur.fetchall()}
        cur.execute("SELECT id, name FROM flavors")
        flv_names = {fid: fname for fid, fname in cur.fetchall()}
        cur.execute(
            """
            SELECT location_id, flavor_id, ounces_on_hand, avg_cost_per_oz
            FROM inventory_state
            ORDER BY location_id, flavor_id
            """
        )
        rows = cur.fetchall()
    out = []
    for loc_id, flavor_id, ounces_on_hand, avg_cost_per_oz in rows:
        out.append({
            "Location": loc_names.get(loc_id, f"Loc {loc_id}"),
            "Flavor": flv_names.get(flavor_id, f"Flavor {flavor_id}"),
            "Ounces on Hand": round(float(ounces_on_hand), 2),
            "Containers (approx)": round(float(ounces_on_hand) / OZ_PER_CONTAINER, 2),
            "Avg Cost / oz": round(float(avg_cost_per_oz), 4),
        })
    return out

################### GUI ###################
class RoleDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Who are you?")
        self.resizable(False, False)
        self.role = None
        ttk.Label(self, text="Select user type").grid(row=0, column=0, columnspan=2, padx=12, pady=12)
        ttk.Button(self, text="Customer", command=self._as_customer).grid(row=1, column=0, padx=8, pady=8, sticky="ew")
        ttk.Button(self, text="Manager", command=self._as_manager).grid(row=1, column=1, padx=8, pady=8, sticky="ew")
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.transient(master)
        self.wait_visibility(); self.focus_set()

    def _close(self):
        self.role = None
        self.destroy()

    def _as_customer(self):
        self.role = "customer"
        self.destroy()

    def _as_manager(self):
        # simple credentials
        user = simpledialog.askstring("Login", "Manager username:", parent=self)
        pwd = None
        if user is not None:
            pwd = simpledialog.askstring("Login", "Manager password:", parent=self, show="*")
        if user == "manager" and pwd == "password":
            self.role = "manager"
            self.destroy()
        else:
            messagebox.showerror("Login failed", "Invalid credentials.")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1100x750")
        self.resizable(True, True)
        self.cart = []  # list of dict lines for customer checkout
        self._select_role_and_build()

    # Role selection 
    def _select_role_and_build(self):
        dlg = RoleDialog(self)
        self.wait_window(dlg)
        role = dlg.role
        if role is None:
            self.destroy(); return
        self.role = role
        self._build_ui_for_role()

    # Build UI according to role 
    def _build_ui_for_role(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True)

        if self.role == "manager":
            self.tab_locations = ttk.Frame(self.nb)
            self.tab_restock = ttk.Frame(self.nb)  # Inventory Restock
            self.tab_import_export = ttk.Frame(self.nb)
            self.tab_reports = ttk.Frame(self.nb)

            self.nb.add(self.tab_locations, text="Locations")
            self.nb.add(self.tab_restock, text="Inventory Restock")
            self.nb.add(self.tab_import_export, text="Import/Export")
            self.nb.add(self.tab_reports, text="Reports")

            self._build_locations_tab()
            self._build_restock_tab()
            self._build_import_export_tab()
            self._build_reports_tab()
        else:
            # Customer
            self.tab_purchase = ttk.Frame(self.nb)
            self.tab_checkout = ttk.Frame(self.nb)
            self.nb.add(self.tab_purchase, text="Purchase")
            self.nb.add(self.tab_checkout, text="Checkout")
            self._build_purchase_tab_customer()
            self._build_checkout_tab()

    # Locations (manager)
    def _build_locations_tab(self):
        frm = self.tab_locations
        ttk.Label(frm, text="Add New Location").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.loc_name_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.loc_name_var, width=40).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        ttk.Button(frm, text="Add", command=self.add_location_cb).grid(row=1, column=1, padx=10, pady=5)
        ttk.Separator(frm, orient=tk.HORIZONTAL).grid(row=2, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(frm, text="Existing Locations").grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.locs_list = tk.Listbox(frm, width=50, height=15)
        self.locs_list.grid(row=4, column=0, padx=10, pady=5, sticky="w")
        self.refresh_locations_list()

    def add_location_cb(self):
        name = self.loc_name_var.get().strip()
        if not name:
            messagebox.showwarning("Validation", "Location name required.")
            return
        if add_location(name):
            self.loc_name_var.set("")
            self.refresh_locations_list()
            messagebox.showinfo("Success", "Location added.")
        else:
            messagebox.showerror("Error", "Location already exists or failed to add.")

    def refresh_locations_list(self):
        self.locs_list.delete(0, tk.END)
        with get_conn() as con:
            for _id, name in list_locations(con):
                self.locs_list.insert(tk.END, f"{_id} – {name}")

    # Inventory Restock (manager)
    def _build_restock_tab(self):
        frm = self.tab_restock
        with get_conn() as con:
            self.loc_choices_mgr = list_locations(con)
            self.flavor_choices_mgr = list_flavors(con)
        ttk.Label(frm, text="Record Inventory Restock").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        ttk.Label(frm, text="Location").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.restock_loc = ttk.Combobox(frm, values=[f"{i}: {n}" for i, n in self.loc_choices_mgr], state="readonly", width=30)
        self.restock_loc.grid(row=1, column=1, padx=10, pady=5)
        ttk.Label(frm, text="Flavor").grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.restock_flavor = ttk.Combobox(frm, values=[f"{i}: {n}" for i, n in self.flavor_choices_mgr], state="readonly", width=30)
        self.restock_flavor.grid(row=2, column=1, padx=10, pady=5)
        ttk.Label(frm, text="# Containers (5 gal each)").grid(row=3, column=0, padx=10, pady=5, sticky="e")
        self.restock_qty_var = tk.IntVar(value=1)
        ttk.Entry(frm, textvariable=self.restock_qty_var, width=10).grid(row=3, column=1, padx=10, pady=5, sticky="w")
        ttk.Button(frm, text="Save Restock", command=self.save_restock_cb).grid(row=4, column=1, padx=10, pady=10, sticky="w")

    def save_restock_cb(self):
        if not self.restock_loc.get() or not self.restock_flavor.get():
            messagebox.showwarning("Validation", "Select location and flavor.")
            return
        loc_id = int(self.restock_loc.get().split(":")[0])
        flavor_id = int(self.restock_flavor.get().split(":")[0])
        qty = int(self.restock_qty_var.get())
        if qty <= 0:
            messagebox.showwarning("Validation", "Quantity must be positive.")
            return
        record_purchase(loc_id, flavor_id, qty)
        messagebox.showinfo("Saved", "Inventory restocked.")

    # Import / Export (manager)
    def _build_import_export_tab(self):
        frm = self.tab_import_export
        ttk.Label(frm, text="CSV Import/Export").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        ttk.Button(frm, text="Export Purchases CSV", command=self.export_purchases).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        ttk.Button(frm, text="Export Sales CSV", command=self.export_sales).grid(row=2, column=0, padx=10, pady=5, sticky="w")
        ttk.Button(frm, text="Export Locations CSV", command=self.export_locations).grid(row=3, column=0, padx=10, pady=5, sticky="w")
        ttk.Separator(frm, orient=tk.HORIZONTAL).grid(row=4, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Button(frm, text="Import Purchases CSV", command=self.import_purchases).grid(row=5, column=0, padx=10, pady=5, sticky="w")
        ttk.Button(frm, text="Import Sales CSV", command=self.import_sales).grid(row=6, column=0, padx=10, pady=5, sticky="w")

    def export_purchases(self):
        ensure_dirs()
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialdir=str(DATA_DIR), initialfile="purchases.csv")
        if not path:
            return
        with get_conn() as con:
            cur = con.cursor()
            cur.execute("SELECT location_id, flavor_id, purchase_date, containers, cost_per_container FROM purchases ORDER BY purchase_date")
            rows = cur.fetchall()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["location_id", "flavor_id", "purchase_date", "containers", "cost_per_container"])
            w.writerows(rows)
        messagebox.showinfo("Export", f"Saved {len(rows)} rows to {path}")

    def export_sales(self):
        ensure_dirs()
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialdir=str(DATA_DIR), initialfile="sales.csv")
        if not path:
            return
        with get_conn() as con:
            cur = con.cursor()
            cur.execute("SELECT location_id, flavor_id, sale_date, size, container_type_id, quantity FROM sales ORDER BY sale_date")
            rows = cur.fetchall()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["location_id", "flavor_id", "sale_date", "size", "container_type_id", "quantity"])
            w.writerows(rows)
        messagebox.showinfo("Export", f"Saved {len(rows)} rows to {path}")

    def export_locations(self):
        ensure_dirs()
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialdir=str(DATA_DIR), initialfile="locations.csv")
        if not path:
            return
        with get_conn() as con:
            rows = list_locations(con)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "name"])
            w.writerows(rows)
        messagebox.showinfo("Export", f"Saved {len(rows)} rows to {path}")

    def import_purchases(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if not path:
            return
        imported = 0
        with open(path, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                try:
                    record_purchase(
                        int(row["location_id"]),
                        int(row["flavor_id"]),
                        int(row["containers"]),
                        row.get("purchase_date") or None,
                    )
                    imported += 1
                except Exception as e:
                    print("Purchase import error:", e)
        messagebox.showinfo("Import", f"Imported {imported} purchase rows.")

    def import_sales(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if not path:
            return
        imported = 0
        with open(path, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                try:
                    record_sale(
                        int(row["location_id"]),
                        int(row["flavor_id"]),
                        row["size"],
                        int(row["container_type_id"]),
                        int(row["quantity"]),
                        row.get("sale_date") or None,
                    )
                    imported += 1
                except Exception as e:
                    print("Sale import error:", e)
        messagebox.showinfo("Import", f"Imported {imported} sale rows.")

    # Reports (manager) 
    def _build_reports_tab(self):
        frm = self.tab_reports
        ttk.Label(frm, text="Reports – Monthly").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        now = datetime.now()
        self.rep_year = tk.IntVar(value=now.year)
        self.rep_month = tk.IntVar(value=now.month)
        ttk.Label(frm, text="Year").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        ttk.Entry(frm, textvariable=self.rep_year, width=8).grid(row=1, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(frm, text="Month").grid(row=1, column=2, padx=10, pady=5, sticky="e")
        ttk.Entry(frm, textvariable=self.rep_month, width=4).grid(row=1, column=3, padx=5, pady=5, sticky="w")
        btns = ttk.Frame(frm); btns.grid(row=2, column=0, columnspan=4, padx=10, pady=10, sticky="w")
        ttk.Button(btns, text="Income Statement", command=self.show_income_statement).grid(row=0, column=0, padx=5)
        ttk.Button(btns, text="Inventory Levels", command=self.show_inventory_levels).grid(row=0, column=2, padx=5)
        ttk.Button(btns, text="Flavor Sales Report", command=self.show_flavor_sales).grid(row=0, column=1, padx=5)
        self.report_text = tk.Text(frm, wrap="word", height=25)
        self.report_text.grid(row=3, column=0, columnspan=4, padx=10, pady=10, sticky="nsew")
        frm.rowconfigure(3, weight=1)
        frm.columnconfigure(3, weight=1)

    def show_income_statement(self):
        y, m = self.rep_year.get(), self.rep_month.get()
        try:
            statements, company = generate_income_statement(y, m)
        except Exception as e:
            messagebox.showerror("Report", str(e))
            return
        lines = [f"Income Statement – {y}-{m:02d}", ""]
        for loc_name, st in statements:
            lines.append(f"Location: {loc_name}")
            lines.append(f"  Revenue:               ${st['revenue']:.2f}")
            lines.append(f"  COGS – Ice Cream:      ${st['cogs_icecream']:.2f}")
            lines.append(f"  COGS – Containers:     ${st['cogs_containers']:.2f}")
            lines.append(f"  COGS – Napkins:        ${st['cogs_napkins']:.2f}")
            lines.append(f"  Gross Profit:          ${st['gross_profit']:.2f}")
            lines.append(f"  Operating Expenses:    ${st['operating_expenses']:.2f}")
            lines.append(f"  Operating Income:      ${st['operating_income']:.2f}")
            lines.append(f"  Net Income:            ${st['net_income']:.2f}")
            lines.append("")
        lines.append("Company Totals:")
        lines.append(f"  Revenue:               ${company['revenue']:.2f}")
        lines.append(f"  COGS – Ice Cream:      ${company['cogs_icecream']:.2f}")
        lines.append(f"  COGS – Containers:     ${company['cogs_containers']:.2f}")
        lines.append(f"  COGS – Napkins:        ${company['cogs_napkins']:.2f}")
        lines.append(f"  Gross Profit:          ${company['gross_profit']:.2f}")
        lines.append(f"  Operating Expenses:    ${company['operating_expenses']:.2f}")
        lines.append(f"  Operating Income:      ${company['operating_income']:.2f}")
        lines.append(f"  Net Income:            ${company['net_income']:.2f}")
        self.report_text.delete("1.0", tk.END)
        self.report_text.insert(tk.END, "\n".join(lines))    

    def show_flavor_sales(self):
        y, m = self.rep_year.get(), self.rep_month.get()
        try:
            rows = generate_flavor_sales_report(y, m)
        except Exception as e:
            messagebox.showerror("Report", str(e)); return
        if not rows:
            txt = f"No sales for {y}-{m:02d}."
        else:
            header = ["Location", "Flavor", "Ounces Sold", "Containers (approx) "]
            lines = [", ".join(header)]
            for r in rows:
                lines.append("\n")
                lines.append(f"{r['Location']}, {r['Flavor']}, {r['Ounces Sold']}, {r['Containers (approx)']}")
            txt = "".join(lines)
        self.report_text.delete("1.0", tk.END); self.report_text.insert(tk.END, txt)
    
    def show_inventory_levels(self):
        try:
            rows = generate_inventory_levels()
        except Exception as e:
            messagebox.showerror("Report", str(e)); return
        if not rows:
            txt = "No inventory records found."
        else:
            header = ["Location", "Flavor", "Ounces on Hand", "Containers (approx)", "Avg Cost / oz"]
            lines = [", ".join(header)]
            for r in rows:
                lines.append("\n")
                lines.append(f"{r['Location']}, {r['Flavor']}, {r['Ounces on Hand']}, {r['Containers (approx)']}, ${r['Avg Cost / oz']}")
            txt = "".join(lines)
        self.report_text.delete("1.0", tk.END); self.report_text.insert(tk.END, txt)


    # Purchase (customer)
    def _build_purchase_tab_customer(self):
        frm = self.tab_purchase
        with get_conn() as con:
            self.loc_choices_cust = list_locations(con)
            self.flavor_choices_cust = list_flavors(con)
            self.container_choices_cust = list_containers(con)
        ttk.Label(frm, text="Make a Purchase").grid(row=0, column=0, padx=10, pady=10, sticky="w")

        ttk.Label(frm, text="Location").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.cust_loc = ttk.Combobox(frm, values=[f"{i}: {n}" for i, n in self.loc_choices_cust], state="readonly", width=30)
        self.cust_loc.grid(row=1, column=1, padx=10, pady=5)

        ttk.Label(frm, text="Flavor").grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.cust_flavor = ttk.Combobox(frm, values=[f"{i}: {n}" for i, n in self.flavor_choices_cust], state="readonly", width=30)
        self.cust_flavor.grid(row=2, column=1, padx=10, pady=5)

        ttk.Label(frm, text="Size").grid(row=3, column=0, padx=10, pady=5, sticky="e")
        self.cust_size = ttk.Combobox(frm, values=list(SALE_PRICES.keys()), state="readonly", width=20)
        self.cust_size.grid(row=3, column=1, padx=10, pady=5, sticky="w")

        ttk.Label(frm, text="Container Type").grid(row=4, column=0, padx=10, pady=5, sticky="e")
        self.cust_container = ttk.Combobox(frm, values=[f"{cid}: {name}" for cid, name, _p, _u in self.container_choices_cust], state="readonly", width=30)
        self.cust_container.grid(row=4, column=1, padx=10, pady=5, sticky="w")

        ttk.Label(frm, text="Quantity").grid(row=5, column=0, padx=10, pady=5, sticky="e")
        self.cust_qty_var = tk.IntVar(value=1)
        ttk.Entry(frm, textvariable=self.cust_qty_var, width=10).grid(row=5, column=1, padx=10, pady=5, sticky="w")

        btns = ttk.Frame(frm); btns.grid(row=6, column=1, padx=10, pady=10, sticky="w")
        ttk.Button(btns, text="Add to Cart", command=self.add_to_cart).grid(row=0, column=0, padx=5)
        ttk.Button(btns, text="Go to Checkout →", command=lambda: self.nb.select(self.tab_checkout)).grid(row=0, column=1, padx=5)

    def add_to_cart(self):
        try:
            loc_id = int(self.cust_loc.get().split(":")[0])
            flavor_id = int(self.cust_flavor.get().split(":")[0])
            size = self.cust_size.get()
            container_type_id = int(self.cust_container.get().split(":")[0])
            qty = int(self.cust_qty_var.get())
        except Exception:
            messagebox.showwarning("Validation", "Please complete all fields correctly.")
            return
        if qty <= 0:
            messagebox.showwarning("Validation", "Quantity must be positive.")
            return
        # Do not write to DB yet; just stage in cart
        line = {
            "location_id": loc_id,
            "flavor_id": flavor_id,
            "size": size,
            "container_type_id": container_type_id,
            "quantity": qty,
        }
        self.cart.append(line)
        messagebox.showinfo("Cart", "Item added to cart.")
        self.refresh_checkout()

    # Checkout (customer)
    def _build_checkout_tab(self):
        frm = self.tab_checkout
        ttk.Label(frm, text="Your Cart").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        cols = ("Location","Flavor","Size","Container","Qty","Price","Line Total")
        self.cart_tree = ttk.Treeview(frm, columns=cols, show="headings", height=16)
        for c in cols:
            self.cart_tree.heading(c, text=c)
            self.cart_tree.column(c, anchor="center", width=140)
        self.cart_tree.grid(row=1, column=0, columnspan=4, padx=10, pady=5, sticky="nsew")
        frm.rowconfigure(1, weight=1)
        frm.columnconfigure(3, weight=1)

        btns = ttk.Frame(frm); btns.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        ttk.Button(btns, text="Delete Selected", command=self.delete_selected_cart_item).grid(row=0, column=0, padx=5)
        ttk.Button(btns, text="- Qty", command=lambda: self.adjust_qty(-1)).grid(row=0, column=1, padx=5)
        ttk.Button(btns, text="+ Qty", command=lambda: self.adjust_qty(+1)).grid(row=0, column=2, padx=5)

        self.total_var = tk.StringVar(value="$0.00")
        ttk.Label(frm, text="Total:").grid(row=3, column=2, padx=10, pady=10, sticky="e")
        ttk.Label(frm, textvariable=self.total_var, font=("TkDefaultFont", 12, "bold")).grid(row=3, column=3, padx=10, pady=10, sticky="w")

        actions = ttk.Frame(frm); actions.grid(row=4, column=0, columnspan=4, padx=10, pady=10, sticky="e")
        ttk.Button(actions, text="Process Order", command=self.process_order).grid(row=0, column=1, padx=5)

    def refresh_checkout(self):
        # Clear
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)
        # Lookups for display
        with get_conn() as con:
            loc_names = dict(list_locations(con))
            flv_names = dict(list_flavors(con))
            cont_map = {cid: name for cid, name, _p, _u in list_containers(con)}
        total = 0.0
        for idx, line in enumerate(self.cart):
            price = SALE_PRICES.get(line["size"], 0.0)
            line_total = price * line["quantity"]
            total += line_total
            self.cart_tree.insert("", tk.END, iid=str(idx), values=(
                loc_names.get(line["location_id"], line["location_id"]),
                flv_names.get(line["flavor_id"], line["flavor_id"]),
                line["size"],
                cont_map.get(line["container_type_id"], line["container_type_id"]),
                line["quantity"],
                f"${price:.2f}",
                f"${line_total:.2f}",
            ))
        self.total_var.set(f"${total:.2f}")

    def delete_selected_cart_item(self):
        sel = self.cart_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.cart):
            del self.cart[idx]
        self.refresh_checkout()

    def adjust_qty(self, delta):
        sel = self.cart_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.cart):
            self.cart[idx]["quantity"] += delta
            if self.cart[idx]["quantity"] <= 0:
                del self.cart[idx]
        self.refresh_checkout()

    def process_order(self):
        if not self.cart:
            messagebox.showinfo("Checkout", "Your cart is empty.")
            return
        # Try to commit each line to DB (will error on insufficient inventory)
        try:
            for line in self.cart:
                record_sale(
                    line["location_id"],
                    line["flavor_id"],
                    line["size"],
                    line["container_type_id"],
                    line["quantity"],
                )
        except ValueError as e:
            messagebox.showerror("Checkout", f"Order failed: {e} No items were charged.")
            return
        self.cart.clear()
        self.refresh_checkout()
        messagebox.showinfo("Checkout", "Thank you! Your order has been processed.")


def main():
    ensure_dirs()
    init_db()
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()

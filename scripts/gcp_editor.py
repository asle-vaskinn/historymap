#!/usr/bin/env python3
"""
Interactive GCP (Ground Control Point) editor for georeferencing historical maps.

A simple GUI using tkinter to:
- Load a historical map image
- Click to place GCP markers
- Enter geographic coordinates for each point
- Save/load GCP JSON files compatible with georeference_map.py

Usage:
    python gcp_editor.py --image data/kartverket/raw/trondheim_1880.png
    python gcp_editor.py --image map.png --output gcps/map.gcp.json
    python gcp_editor.py --load gcps/existing.gcp.json
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from datetime import datetime
import re

from PIL import Image, ImageTk, ImageDraw
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog


class GCP:
    """A single Ground Control Point."""

    def __init__(
        self,
        gcp_id: str,
        pixel_x: int,
        pixel_y: int,
        geo_x: Optional[float] = None,
        geo_y: Optional[float] = None,
        description: str = ""
    ):
        self.id = gcp_id
        self.pixel_x = pixel_x
        self.pixel_y = pixel_y
        self.geo_x = geo_x  # longitude
        self.geo_y = geo_y  # latitude
        self.description = description

    def is_complete(self) -> bool:
        """Check if GCP has both pixel and geo coordinates."""
        return self.geo_x is not None and self.geo_y is not None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        d = {
            "id": self.id,
            "pixel_x": self.pixel_x,
            "pixel_y": self.pixel_y,
        }
        if self.geo_x is not None:
            d["geo_x"] = self.geo_x
        if self.geo_y is not None:
            d["geo_y"] = self.geo_y
        if self.description:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> 'GCP':
        """Create GCP from dictionary."""
        return cls(
            gcp_id=d.get("id", ""),
            pixel_x=d.get("pixel_x", 0),
            pixel_y=d.get("pixel_y", 0),
            geo_x=d.get("geo_x"),
            geo_y=d.get("geo_y"),
            description=d.get("description", "")
        )


class GCPEditor:
    """Interactive GCP editor using tkinter."""

    MARKER_RADIUS = 8
    MARKER_COLOR_INCOMPLETE = "#FF6B6B"  # Red for incomplete
    MARKER_COLOR_COMPLETE = "#4ECDC4"    # Teal for complete
    MARKER_COLOR_SELECTED = "#FFE66D"    # Yellow for selected

    def __init__(self, image_path: Optional[str] = None, output_path: Optional[str] = None):
        """
        Initialize GCP editor.

        Args:
            image_path: Path to historical map image
            output_path: Path for output GCP JSON file
        """
        self.image_path = Path(image_path) if image_path else None
        self.output_path = Path(output_path) if output_path else None

        # State
        self.image: Optional[Image.Image] = None
        self.photo: Optional[ImageTk.PhotoImage] = None
        self.gcps: List[GCP] = []
        self.selected_gcp: Optional[int] = None  # Index of selected GCP
        self.gcp_counter = 0
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.dragging = False
        self.drag_start = (0, 0)

        # Metadata
        self.map_id = ""
        self.map_date = 1900
        self.crs = "EPSG:4326"

        # Setup GUI
        self.setup_gui()

        # Load image if provided
        if self.image_path and self.image_path.exists():
            self.load_image(self.image_path)

    def setup_gui(self):
        """Setup tkinter GUI."""
        self.root = tk.Tk()
        self.root.title("GCP Editor - Ground Control Point Tool")
        self.root.geometry("1200x800")

        # Main layout
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left panel - Controls
        left_frame = ttk.Frame(main_frame, width=300)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        left_frame.pack_propagate(False)

        # Right panel - Canvas
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.setup_controls(left_frame)
        self.setup_canvas(right_frame)

        # Keyboard bindings
        self.root.bind('<Key>', self.on_key_press)
        self.root.bind('<Delete>', lambda e: self.delete_selected_gcp())
        self.root.bind('<BackSpace>', lambda e: self.delete_selected_gcp())

        # Window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_controls(self, parent):
        """Setup control panel."""
        # Title
        title = ttk.Label(parent, text="GCP Editor", font=('Arial', 14, 'bold'))
        title.pack(pady=10)

        # File controls
        file_frame = ttk.LabelFrame(parent, text="File", padding=10)
        file_frame.pack(fill='x', pady=5)

        ttk.Button(file_frame, text="Open Image...", command=self.open_image_dialog).pack(fill='x', pady=2)
        ttk.Button(file_frame, text="Load GCPs...", command=self.load_gcps_dialog).pack(fill='x', pady=2)
        ttk.Button(file_frame, text="Save GCPs (Ctrl+S)", command=self.save_gcps).pack(fill='x', pady=2)
        ttk.Button(file_frame, text="Save GCPs As...", command=self.save_gcps_as).pack(fill='x', pady=2)

        ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=10)

        # Metadata
        meta_frame = ttk.LabelFrame(parent, text="Map Metadata", padding=10)
        meta_frame.pack(fill='x', pady=5)

        ttk.Label(meta_frame, text="Map ID:").pack(anchor='w')
        self.map_id_var = tk.StringVar(value=self.map_id)
        ttk.Entry(meta_frame, textvariable=self.map_id_var).pack(fill='x', pady=2)

        ttk.Label(meta_frame, text="Map Year:").pack(anchor='w')
        self.map_date_var = tk.StringVar(value=str(self.map_date))
        ttk.Entry(meta_frame, textvariable=self.map_date_var).pack(fill='x', pady=2)

        ttk.Label(meta_frame, text="CRS:").pack(anchor='w')
        self.crs_var = tk.StringVar(value=self.crs)
        crs_combo = ttk.Combobox(meta_frame, textvariable=self.crs_var,
                                  values=["EPSG:4326", "EPSG:25832", "EPSG:25833"])
        crs_combo.pack(fill='x', pady=2)

        ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=10)

        # GCP List
        gcp_frame = ttk.LabelFrame(parent, text="Ground Control Points", padding=10)
        gcp_frame.pack(fill='both', expand=True, pady=5)

        # Listbox with scrollbar
        list_frame = ttk.Frame(gcp_frame)
        list_frame.pack(fill='both', expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.gcp_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                                       selectmode=tk.SINGLE, height=10)
        self.gcp_listbox.pack(fill='both', expand=True)
        scrollbar.config(command=self.gcp_listbox.yview)

        self.gcp_listbox.bind('<<ListboxSelect>>', self.on_gcp_select)

        # GCP count
        self.gcp_count_label = ttk.Label(gcp_frame, text="0 GCPs (0 complete)")
        self.gcp_count_label.pack(pady=5)

        # GCP buttons
        btn_frame = ttk.Frame(gcp_frame)
        btn_frame.pack(fill='x', pady=5)

        ttk.Button(btn_frame, text="Edit", command=self.edit_selected_gcp).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete", command=self.delete_selected_gcp).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Clear All", command=self.clear_all_gcps).pack(side=tk.RIGHT, padx=2)

        ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=10)

        # Instructions
        help_frame = ttk.LabelFrame(parent, text="Instructions", padding=10)
        help_frame.pack(fill='x', pady=5)

        help_text = """
Click on map to add GCP
Double-click GCP to edit coords
Right-click to delete GCP
Mouse wheel to zoom
Middle-drag to pan

Keyboard:
  +/- : Zoom in/out
  Delete: Remove selected
  Ctrl+S: Save
  Ctrl+Z: Undo last
"""
        ttk.Label(help_frame, text=help_text.strip(), justify=tk.LEFT,
                  font=('Courier', 9)).pack()

        ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=10)

        # Zoom controls
        zoom_frame = ttk.LabelFrame(parent, text="View", padding=10)
        zoom_frame.pack(fill='x', pady=5)

        self.zoom_label = ttk.Label(zoom_frame, text="Zoom: 100%")
        self.zoom_label.pack()

        zoom_btn_frame = ttk.Frame(zoom_frame)
        zoom_btn_frame.pack(fill='x', pady=5)

        ttk.Button(zoom_btn_frame, text="-", width=3, command=self.zoom_out).pack(side=tk.LEFT, padx=5)
        ttk.Button(zoom_btn_frame, text="Fit", command=self.fit_to_window).pack(side=tk.LEFT, padx=5)
        ttk.Button(zoom_btn_frame, text="+", width=3, command=self.zoom_in).pack(side=tk.LEFT, padx=5)

    def setup_canvas(self, parent):
        """Setup image canvas."""
        # Canvas with scrollbars
        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        self.h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        self.v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas = tk.Canvas(
            canvas_frame,
            bg='#2C3E50',
            cursor='crosshair',
            xscrollcommand=self.h_scroll.set,
            yscrollcommand=self.v_scroll.set
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.h_scroll.config(command=self.canvas.xview)
        self.v_scroll.config(command=self.canvas.yview)

        # Mouse bindings
        self.canvas.bind('<Button-1>', self.on_canvas_click)
        self.canvas.bind('<Double-Button-1>', self.on_canvas_double_click)
        self.canvas.bind('<Button-3>', self.on_canvas_right_click)
        self.canvas.bind('<Button-2>', self.on_pan_start)
        self.canvas.bind('<B2-Motion>', self.on_pan_drag)
        self.canvas.bind('<MouseWheel>', self.on_mouse_wheel)  # Windows/macOS
        self.canvas.bind('<Button-4>', lambda e: self.zoom_in())  # Linux scroll up
        self.canvas.bind('<Button-5>', lambda e: self.zoom_out())  # Linux scroll down

        # Status bar
        self.status_var = tk.StringVar(value="Load an image to begin")
        status_bar = ttk.Label(parent, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=2)

    def load_image(self, path: Path):
        """Load image file."""
        try:
            self.image = Image.open(path).convert('RGB')
            self.image_path = path

            # Extract map_id from filename
            self.map_id = path.stem
            self.map_id_var.set(self.map_id)

            # Try to extract year from filename
            year_match = re.search(r'(18\d{2}|19\d{2}|20\d{2})', path.stem)
            if year_match:
                self.map_date = int(year_match.group(1))
                self.map_date_var.set(str(self.map_date))

            # Set default output path
            if self.output_path is None:
                gcps_dir = path.parent.parent / 'gcps'
                gcps_dir.mkdir(parents=True, exist_ok=True)
                self.output_path = gcps_dir / f"{path.stem}.gcp.json"

            self.root.title(f"GCP Editor - {path.name}")
            self.fit_to_window()
            self.status_var.set(f"Loaded: {path.name} ({self.image.width}x{self.image.height})")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image: {e}")

    def open_image_dialog(self):
        """Open file dialog to select image."""
        path = filedialog.askopenfilename(
            title="Open Historical Map Image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.tif *.tiff"),
                ("All files", "*.*")
            ]
        )
        if path:
            self.load_image(Path(path))

    def fit_to_window(self):
        """Fit image to canvas window."""
        if self.image is None:
            return

        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()

        if canvas_w < 10 or canvas_h < 10:
            # Window not ready yet
            self.root.after(100, self.fit_to_window)
            return

        # Calculate zoom to fit
        zoom_x = canvas_w / self.image.width
        zoom_y = canvas_h / self.image.height
        self.zoom_level = min(zoom_x, zoom_y) * 0.95

        self.update_display()

    def zoom_in(self):
        """Zoom in."""
        self.zoom_level *= 1.25
        self.update_display()

    def zoom_out(self):
        """Zoom out."""
        self.zoom_level *= 0.8
        self.update_display()

    def update_display(self):
        """Redraw canvas with current zoom and GCPs."""
        if self.image is None:
            return

        # Calculate display size
        display_w = int(self.image.width * self.zoom_level)
        display_h = int(self.image.height * self.zoom_level)

        # Resize image
        display_image = self.image.resize((display_w, display_h), Image.LANCZOS)

        # Draw GCP markers
        draw = ImageDraw.Draw(display_image)

        for i, gcp in enumerate(self.gcps):
            x = int(gcp.pixel_x * self.zoom_level)
            y = int(gcp.pixel_y * self.zoom_level)
            r = self.MARKER_RADIUS

            # Determine color
            if i == self.selected_gcp:
                color = self.MARKER_COLOR_SELECTED
            elif gcp.is_complete():
                color = self.MARKER_COLOR_COMPLETE
            else:
                color = self.MARKER_COLOR_INCOMPLETE

            # Draw crosshair marker
            draw.ellipse([x-r, y-r, x+r, y+r], outline=color, width=2)
            draw.line([x-r-4, y, x+r+4, y], fill=color, width=2)
            draw.line([x, y-r-4, x, y+r+4], fill=color, width=2)

            # Draw label
            label = gcp.id if gcp.id else f"GCP{i+1}"
            draw.text((x+r+4, y-r), label, fill=color)

        # Convert to PhotoImage
        self.photo = ImageTk.PhotoImage(display_image)

        # Update canvas
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        self.canvas.config(scrollregion=(0, 0, display_w, display_h))

        # Update zoom label
        self.zoom_label.config(text=f"Zoom: {int(self.zoom_level * 100)}%")

    def canvas_to_pixel(self, canvas_x: int, canvas_y: int) -> Tuple[int, int]:
        """Convert canvas coordinates to image pixel coordinates."""
        # Account for scroll position
        canvas_x = self.canvas.canvasx(canvas_x)
        canvas_y = self.canvas.canvasy(canvas_y)

        pixel_x = int(canvas_x / self.zoom_level)
        pixel_y = int(canvas_y / self.zoom_level)

        return pixel_x, pixel_y

    def on_canvas_click(self, event):
        """Handle canvas click - add new GCP or select existing."""
        if self.image is None:
            return

        pixel_x, pixel_y = self.canvas_to_pixel(event.x, event.y)

        # Check bounds
        if pixel_x < 0 or pixel_x >= self.image.width:
            return
        if pixel_y < 0 or pixel_y >= self.image.height:
            return

        # Check if clicking on existing GCP
        clicked_gcp = self.find_gcp_at(pixel_x, pixel_y)

        if clicked_gcp is not None:
            # Select existing GCP
            self.selected_gcp = clicked_gcp
            self.gcp_listbox.selection_clear(0, tk.END)
            self.gcp_listbox.selection_set(clicked_gcp)
            self.gcp_listbox.see(clicked_gcp)
        else:
            # Add new GCP
            self.add_gcp(pixel_x, pixel_y)

        self.update_display()
        self.update_gcp_list()

    def on_canvas_double_click(self, event):
        """Handle double-click - edit GCP coordinates."""
        if self.image is None:
            return

        pixel_x, pixel_y = self.canvas_to_pixel(event.x, event.y)
        clicked_gcp = self.find_gcp_at(pixel_x, pixel_y)

        if clicked_gcp is not None:
            self.selected_gcp = clicked_gcp
            self.edit_selected_gcp()

    def on_canvas_right_click(self, event):
        """Handle right-click - delete GCP."""
        if self.image is None:
            return

        pixel_x, pixel_y = self.canvas_to_pixel(event.x, event.y)
        clicked_gcp = self.find_gcp_at(pixel_x, pixel_y)

        if clicked_gcp is not None:
            self.selected_gcp = clicked_gcp
            self.delete_selected_gcp()

    def on_pan_start(self, event):
        """Start panning with middle mouse button."""
        self.dragging = True
        self.drag_start = (event.x, event.y)
        self.canvas.config(cursor='fleur')

    def on_pan_drag(self, event):
        """Handle pan drag."""
        if self.dragging:
            dx = event.x - self.drag_start[0]
            dy = event.y - self.drag_start[1]
            self.canvas.xview_scroll(-dx, 'units')
            self.canvas.yview_scroll(-dy, 'units')
            self.drag_start = (event.x, event.y)

    def on_mouse_wheel(self, event):
        """Handle mouse wheel zoom."""
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def find_gcp_at(self, pixel_x: int, pixel_y: int, threshold: int = 15) -> Optional[int]:
        """Find GCP index at given pixel coordinates."""
        threshold_px = threshold / self.zoom_level

        for i, gcp in enumerate(self.gcps):
            dx = abs(gcp.pixel_x - pixel_x)
            dy = abs(gcp.pixel_y - pixel_y)
            if dx < threshold_px and dy < threshold_px:
                return i

        return None

    def add_gcp(self, pixel_x: int, pixel_y: int):
        """Add new GCP at pixel coordinates."""
        self.gcp_counter += 1
        gcp_id = f"GCP{self.gcp_counter}"

        gcp = GCP(
            gcp_id=gcp_id,
            pixel_x=pixel_x,
            pixel_y=pixel_y
        )

        self.gcps.append(gcp)
        self.selected_gcp = len(self.gcps) - 1

        # Prompt for coordinates
        self.edit_gcp(gcp)

        self.status_var.set(f"Added {gcp_id} at pixel ({pixel_x}, {pixel_y})")

    def edit_gcp(self, gcp: GCP):
        """Open dialog to edit GCP coordinates."""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit GCP: {gcp.id}")
        dialog.geometry("350x280")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # GCP ID
        ttk.Label(frame, text="GCP ID:").grid(row=0, column=0, sticky='w', pady=5)
        id_var = tk.StringVar(value=gcp.id)
        ttk.Entry(frame, textvariable=id_var, width=20).grid(row=0, column=1, pady=5)

        # Pixel coordinates (read-only)
        ttk.Label(frame, text="Pixel X:").grid(row=1, column=0, sticky='w', pady=5)
        ttk.Label(frame, text=str(gcp.pixel_x)).grid(row=1, column=1, sticky='w', pady=5)

        ttk.Label(frame, text="Pixel Y:").grid(row=2, column=0, sticky='w', pady=5)
        ttk.Label(frame, text=str(gcp.pixel_y)).grid(row=2, column=1, sticky='w', pady=5)

        ttk.Separator(frame, orient='horizontal').grid(row=3, column=0, columnspan=2, sticky='ew', pady=10)

        # Geographic coordinates
        ttk.Label(frame, text="Longitude (X):").grid(row=4, column=0, sticky='w', pady=5)
        lon_var = tk.StringVar(value=str(gcp.geo_x) if gcp.geo_x else "")
        lon_entry = ttk.Entry(frame, textvariable=lon_var, width=20)
        lon_entry.grid(row=4, column=1, pady=5)

        ttk.Label(frame, text="Latitude (Y):").grid(row=5, column=0, sticky='w', pady=5)
        lat_var = tk.StringVar(value=str(gcp.geo_y) if gcp.geo_y else "")
        lat_entry = ttk.Entry(frame, textvariable=lat_var, width=20)
        lat_entry.grid(row=5, column=1, pady=5)

        # Description
        ttk.Label(frame, text="Description:").grid(row=6, column=0, sticky='w', pady=5)
        desc_var = tk.StringVar(value=gcp.description)
        ttk.Entry(frame, textvariable=desc_var, width=30).grid(row=6, column=1, pady=5)

        # Hint
        hint = ttk.Label(frame, text="Tip: Find coords in Google Maps, right-click → copy",
                         font=('Arial', 9), foreground='gray')
        hint.grid(row=7, column=0, columnspan=2, pady=10)

        def save():
            gcp.id = id_var.get()
            try:
                lon_str = lon_var.get().strip()
                lat_str = lat_var.get().strip()

                if lon_str and lat_str:
                    # Handle pasted coords like "63.4305, 10.3951"
                    if ',' in lon_str and not lat_str:
                        parts = lon_str.split(',')
                        if len(parts) == 2:
                            lat_str = parts[0].strip()
                            lon_str = parts[1].strip()

                    gcp.geo_x = float(lon_str)
                    gcp.geo_y = float(lat_str)
                else:
                    gcp.geo_x = None
                    gcp.geo_y = None

            except ValueError as e:
                messagebox.showerror("Error", f"Invalid coordinates: {e}")
                return

            gcp.description = desc_var.get()
            dialog.destroy()
            self.update_display()
            self.update_gcp_list()

        def cancel():
            dialog.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=8, column=0, columnspan=2, pady=15)

        ttk.Button(btn_frame, text="Save", command=save).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=cancel).pack(side=tk.LEFT, padx=10)

        lon_entry.focus()
        dialog.bind('<Return>', lambda e: save())
        dialog.bind('<Escape>', lambda e: cancel())

    def edit_selected_gcp(self):
        """Edit currently selected GCP."""
        if self.selected_gcp is not None and self.selected_gcp < len(self.gcps):
            self.edit_gcp(self.gcps[self.selected_gcp])

    def delete_selected_gcp(self):
        """Delete currently selected GCP."""
        if self.selected_gcp is not None and self.selected_gcp < len(self.gcps):
            gcp = self.gcps[self.selected_gcp]
            del self.gcps[self.selected_gcp]
            self.selected_gcp = None
            self.update_display()
            self.update_gcp_list()
            self.status_var.set(f"Deleted {gcp.id}")

    def clear_all_gcps(self):
        """Clear all GCPs after confirmation."""
        if not self.gcps:
            return

        if messagebox.askyesno("Confirm", f"Delete all {len(self.gcps)} GCPs?"):
            self.gcps = []
            self.selected_gcp = None
            self.gcp_counter = 0
            self.update_display()
            self.update_gcp_list()
            self.status_var.set("Cleared all GCPs")

    def update_gcp_list(self):
        """Update GCP listbox."""
        self.gcp_listbox.delete(0, tk.END)

        complete_count = 0
        for i, gcp in enumerate(self.gcps):
            status = "✓" if gcp.is_complete() else "○"
            if gcp.is_complete():
                complete_count += 1

            coords = f"({gcp.geo_x:.4f}, {gcp.geo_y:.4f})" if gcp.is_complete() else "(no coords)"
            text = f"{status} {gcp.id}: {coords}"
            self.gcp_listbox.insert(tk.END, text)

        self.gcp_count_label.config(text=f"{len(self.gcps)} GCPs ({complete_count} complete)")

        # Restore selection
        if self.selected_gcp is not None and self.selected_gcp < len(self.gcps):
            self.gcp_listbox.selection_set(self.selected_gcp)

    def on_gcp_select(self, event):
        """Handle GCP listbox selection."""
        selection = self.gcp_listbox.curselection()
        if selection:
            self.selected_gcp = selection[0]
            self.update_display()

    def save_gcps(self):
        """Save GCPs to JSON file."""
        if not self.output_path:
            self.save_gcps_as()
            return

        self._save_to_path(self.output_path)

    def save_gcps_as(self):
        """Save GCPs with file dialog."""
        default_name = f"{self.map_id_var.get()}.gcp.json" if self.map_id_var.get() else "gcps.json"

        path = filedialog.asksaveasfilename(
            title="Save GCPs",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("GCP JSON", "*.gcp.json"), ("JSON files", "*.json")]
        )

        if path:
            self.output_path = Path(path)
            self._save_to_path(self.output_path)

    def _save_to_path(self, path: Path):
        """Save GCPs to specified path."""
        try:
            map_date = int(self.map_date_var.get())
        except ValueError:
            map_date = 1900

        data = {
            "version": "1.0",
            "map_id": self.map_id_var.get(),
            "map_date": map_date,
            "crs": self.crs_var.get(),
            "source_file": str(self.image_path.name) if self.image_path else "",
            "created": datetime.now().isoformat(),
            "gcps": [gcp.to_dict() for gcp in self.gcps]
        }

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

        self.output_path = path
        self.status_var.set(f"Saved to {path.name}")
        messagebox.showinfo("Saved", f"Saved {len(self.gcps)} GCPs to:\n{path}")

    def load_gcps_dialog(self):
        """Load GCPs from file dialog."""
        path = filedialog.askopenfilename(
            title="Load GCPs",
            filetypes=[("GCP JSON", "*.gcp.json"), ("JSON files", "*.json")]
        )

        if path:
            self.load_gcps(Path(path))

    def load_gcps(self, path: Path):
        """Load GCPs from JSON file."""
        try:
            with open(path, 'r') as f:
                data = json.load(f)

            # Load metadata
            self.map_id = data.get('map_id', '')
            self.map_id_var.set(self.map_id)

            self.map_date = data.get('map_date', 1900)
            self.map_date_var.set(str(self.map_date))

            self.crs = data.get('crs', 'EPSG:4326')
            self.crs_var.set(self.crs)

            # Load GCPs
            self.gcps = [GCP.from_dict(g) for g in data.get('gcps', [])]
            self.gcp_counter = len(self.gcps)
            self.selected_gcp = None

            # Try to load corresponding image
            source_file = data.get('source_file', '')
            if source_file and self.image is None:
                image_path = path.parent.parent / 'raw' / source_file
                if image_path.exists():
                    self.load_image(image_path)

            self.output_path = path
            self.update_display()
            self.update_gcp_list()
            self.status_var.set(f"Loaded {len(self.gcps)} GCPs from {path.name}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load GCPs: {e}")

    def on_key_press(self, event):
        """Handle keyboard shortcuts."""
        if event.state & 4:  # Ctrl key
            if event.keysym.lower() == 's':
                self.save_gcps()
            elif event.keysym.lower() == 'z':
                if self.gcps:
                    self.gcps.pop()
                    self.selected_gcp = None
                    self.update_display()
                    self.update_gcp_list()
                    self.status_var.set("Undid last GCP")
        elif event.char == '+' or event.char == '=':
            self.zoom_in()
        elif event.char == '-':
            self.zoom_out()

    def on_closing(self):
        """Handle window close."""
        if self.gcps:
            if messagebox.askyesno("Quit", "Save GCPs before quitting?"):
                self.save_gcps()
        self.root.destroy()

    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description='Interactive GCP editor for georeferencing')

    parser.add_argument('--image', '-i', help='Path to historical map image')
    parser.add_argument('--output', '-o', help='Path for output GCP JSON file')
    parser.add_argument('--load', '-l', help='Load existing GCP file')

    args = parser.parse_args()

    editor = GCPEditor(
        image_path=args.image,
        output_path=args.output
    )

    if args.load:
        editor.load_gcps(Path(args.load))

    editor.run()


if __name__ == '__main__':
    main()

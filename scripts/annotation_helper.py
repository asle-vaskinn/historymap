#!/usr/bin/env python3
"""
Interactive annotation tool for labeling historical map tiles.

A simple GUI using tkinter to:
- Load historical map tiles
- Display ML model predictions as semi-transparent overlays
- Allow manual corrections with brush/eraser tools
- Save corrected masks
- Navigate between tiles

Usage:
    python annotation_helper.py --tiles-dir ../data/kartverket/tiles/ \
                                --output-dir ../data/annotations/ \
                                --model ../models/checkpoints/best_model.pth
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime

import numpy as np
import torch
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Add parent directory to path to import ml module
sys.path.insert(0, str(Path(__file__).parent.parent))
from ml.predict import load_model, load_and_preprocess_image, predict, get_device


# Class definitions
CLASSES = {
    0: {'name': 'background', 'color': (0, 0, 0, 0), 'key': '1'},
    1: {'name': 'building', 'color': (255, 0, 0, 180), 'key': '2'},
    2: {'name': 'road', 'color': (255, 255, 0, 180), 'key': '3'},
    3: {'name': 'water', 'color': (0, 0, 255, 180), 'key': '4'},
    4: {'name': 'forest', 'color': (0, 255, 0, 180), 'key': '5'},
}


class AnnotationHelper:
    """Interactive annotation tool using tkinter."""

    def __init__(self, tiles_dir: str, output_dir: str, model_path: Optional[str] = None):
        """
        Initialize annotation helper.

        Args:
            tiles_dir: Directory containing tile images to annotate
            output_dir: Directory to save annotations
            model_path: Optional path to trained model for predictions
        """
        self.tiles_dir = Path(tiles_dir)
        self.output_dir = Path(output_dir)
        self.model_path = model_path

        # Create output directories
        self.images_dir = self.output_dir / "images"
        self.masks_dir = self.output_dir / "masks"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.masks_dir.mkdir(parents=True, exist_ok=True)

        # Progress tracking
        self.progress_file = self.output_dir / "progress.json"
        self.progress = self.load_progress()

        # Load tile list
        self.tiles = self.load_tiles()
        if not self.tiles:
            raise ValueError(f"No tiles found in {tiles_dir}")

        # Current state
        self.current_index = 0
        self.current_tile = None
        self.current_image = None
        self.original_mask = None  # From model prediction
        self.working_mask = None   # User's edits
        self.brush_size = 10
        self.current_class = 1  # Default to building
        self.drawing = False
        self.last_x = None
        self.last_y = None

        # Model
        self.model = None
        self.device = None
        if model_path and os.path.exists(model_path):
            self.device = get_device()
            print(f"Loading model from {model_path}...")
            self.model = load_model(model_path, self.device)
            print("Model loaded successfully")
        else:
            print("No model provided, starting with blank masks")

        # Setup GUI
        self.setup_gui()

        # Load first tile
        self.load_tile(self.current_index)

    def load_progress(self) -> Dict:
        """Load progress from file."""
        if self.progress_file.exists():
            with open(self.progress_file, 'r') as f:
                return json.load(f)
        return {'annotated': [], 'last_modified': {}}

    def save_progress(self):
        """Save progress to file."""
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)

    def load_tiles(self) -> List[Path]:
        """Load list of tile images."""
        extensions = ['.png', '.jpg', '.jpeg', '.tif', '.tiff']
        tiles = []
        for ext in extensions:
            tiles.extend(self.tiles_dir.glob(f'*{ext}'))
            tiles.extend(self.tiles_dir.glob(f'*{ext.upper()}'))
        return sorted(tiles)

    def setup_gui(self):
        """Setup tkinter GUI."""
        self.root = tk.Tk()
        self.root.title("Historical Map Annotation Helper")

        # Main layout: left panel (controls), right panel (canvas)
        left_frame = ttk.Frame(self.root)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        right_frame = ttk.Frame(self.root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left panel - Controls
        self.setup_controls(left_frame)

        # Right panel - Canvas
        self.canvas = tk.Canvas(right_frame, bg='gray', cursor='crosshair')
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Bind mouse events
        self.canvas.bind('<Button-1>', self.on_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_mouse_up)

        # Bind keyboard shortcuts
        self.root.bind('<Key>', self.on_key_press)

        # Window closing
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_controls(self, parent):
        """Setup control panel."""
        # Title
        title = ttk.Label(parent, text="Annotation Helper", font=('Arial', 14, 'bold'))
        title.pack(pady=10)

        # Progress info
        self.progress_label = ttk.Label(parent, text="Tile: 0 / 0")
        self.progress_label.pack(pady=5)

        self.filename_label = ttk.Label(parent, text="", wraplength=200)
        self.filename_label.pack(pady=5)

        ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=10)

        # Navigation
        nav_frame = ttk.LabelFrame(parent, text="Navigation", padding=10)
        nav_frame.pack(fill='x', pady=5)

        btn_prev = ttk.Button(nav_frame, text="← Previous (A)", command=self.prev_tile)
        btn_prev.pack(fill='x', pady=2)

        btn_next = ttk.Button(nav_frame, text="Next → (D)", command=self.next_tile)
        btn_next.pack(fill='x', pady=2)

        btn_goto = ttk.Button(nav_frame, text="Go to...", command=self.goto_tile)
        btn_goto.pack(fill='x', pady=2)

        ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=10)

        # Class selection
        class_frame = ttk.LabelFrame(parent, text="Class Selection", padding=10)
        class_frame.pack(fill='x', pady=5)

        self.class_buttons = {}
        for class_id, class_info in CLASSES.items():
            color_hex = '#{:02x}{:02x}{:02x}'.format(*class_info['color'][:3])
            btn = ttk.Button(
                class_frame,
                text=f"{class_info['key']}: {class_info['name']}",
                command=lambda cid=class_id: self.set_class(cid)
            )
            btn.pack(fill='x', pady=2)
            self.class_buttons[class_id] = btn

        self.update_class_buttons()

        ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=10)

        # Brush controls
        brush_frame = ttk.LabelFrame(parent, text="Brush", padding=10)
        brush_frame.pack(fill='x', pady=5)

        ttk.Label(brush_frame, text="Size:").pack()
        self.brush_size_var = tk.IntVar(value=self.brush_size)
        brush_slider = ttk.Scale(
            brush_frame,
            from_=1,
            to=50,
            orient='horizontal',
            variable=self.brush_size_var,
            command=self.on_brush_size_change
        )
        brush_slider.pack(fill='x', pady=5)

        self.brush_size_label = ttk.Label(brush_frame, text=f"{self.brush_size} px")
        self.brush_size_label.pack()

        btn_eraser = ttk.Button(brush_frame, text="Eraser (E)", command=self.reset_to_prediction)
        btn_eraser.pack(fill='x', pady=5)

        ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=10)

        # Actions
        action_frame = ttk.LabelFrame(parent, text="Actions", padding=10)
        action_frame.pack(fill='x', pady=5)

        btn_save = ttk.Button(action_frame, text="Save (S)", command=self.save_annotation)
        btn_save.pack(fill='x', pady=2)

        btn_reset = ttk.Button(action_frame, text="Reset", command=self.reset_mask)
        btn_reset.pack(fill='x', pady=2)

        btn_run_model = ttk.Button(action_frame, text="Run Model", command=self.run_model_prediction)
        btn_run_model.pack(fill='x', pady=2)
        if self.model is None:
            btn_run_model.config(state='disabled')

        ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=10)

        # View controls
        view_frame = ttk.LabelFrame(parent, text="View", padding=10)
        view_frame.pack(fill='x', pady=5)

        self.show_mask_var = tk.BooleanVar(value=True)
        chk_mask = ttk.Checkbutton(
            view_frame,
            text="Show Mask (M)",
            variable=self.show_mask_var,
            command=self.update_display
        )
        chk_mask.pack()

        self.opacity_var = tk.IntVar(value=50)
        ttk.Label(view_frame, text="Opacity:").pack()
        opacity_slider = ttk.Scale(
            view_frame,
            from_=0,
            to=100,
            orient='horizontal',
            variable=self.opacity_var,
            command=lambda x: self.update_display()
        )
        opacity_slider.pack(fill='x', pady=5)

        ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=10)

        # Quit
        btn_quit = ttk.Button(parent, text="Quit (Q)", command=self.on_closing)
        btn_quit.pack(fill='x', pady=5)

    def update_class_buttons(self):
        """Update class button styles to highlight selected."""
        for class_id, btn in self.class_buttons.items():
            if class_id == self.current_class:
                btn.state(['pressed'])
            else:
                btn.state(['!pressed'])

    def set_class(self, class_id: int):
        """Set current drawing class."""
        self.current_class = class_id
        self.update_class_buttons()
        color = CLASSES[class_id]['color']
        print(f"Selected class: {CLASSES[class_id]['name']} (RGB: {color[:3]})")

    def on_brush_size_change(self, value):
        """Handle brush size slider change."""
        self.brush_size = int(float(value))
        self.brush_size_label.config(text=f"{self.brush_size} px")

    def load_tile(self, index: int):
        """Load tile at given index."""
        if index < 0 or index >= len(self.tiles):
            return

        self.current_index = index
        self.current_tile = self.tiles[index]

        # Update labels
        self.progress_label.config(
            text=f"Tile: {index + 1} / {len(self.tiles)}"
        )
        self.filename_label.config(text=self.current_tile.name)

        # Load image
        self.current_image = Image.open(self.current_tile).convert('RGB')

        # Check if annotation already exists
        mask_path = self.masks_dir / f"{self.current_tile.stem}_mask.png"
        if mask_path.exists():
            # Load existing annotation
            mask_img = Image.open(mask_path).convert('L')
            self.working_mask = np.array(mask_img)
            self.original_mask = self.working_mask.copy()
            print(f"Loaded existing annotation: {mask_path.name}")
        elif self.model is not None:
            # Run model prediction
            self.run_model_prediction()
        else:
            # Start with blank mask
            w, h = self.current_image.size
            self.working_mask = np.zeros((h, w), dtype=np.uint8)
            self.original_mask = self.working_mask.copy()

        self.update_display()

    def run_model_prediction(self):
        """Run model prediction on current tile."""
        if self.model is None or self.current_image is None:
            return

        print("Running model prediction...")

        # Convert PIL image to tensor
        image_np = np.array(self.current_image).astype(np.float32) / 255.0
        image_tensor = torch.from_numpy(image_np).permute(2, 0, 1).unsqueeze(0)

        # Run prediction
        predicted_mask, _ = predict(self.model, image_tensor, self.device)

        self.original_mask = predicted_mask
        self.working_mask = predicted_mask.copy()

        print("Prediction complete")
        self.update_display()

    def update_display(self):
        """Update canvas with current image and mask overlay."""
        if self.current_image is None:
            return

        # Start with original image
        display_image = self.current_image.copy()

        # Add mask overlay if enabled
        if self.show_mask_var.get() and self.working_mask is not None:
            # Create colored mask overlay
            h, w = self.working_mask.shape
            overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            overlay_array = np.array(overlay)

            for class_id, class_info in CLASSES.items():
                if class_id == 0:  # Skip background
                    continue
                mask = self.working_mask == class_id
                color = class_info['color']
                # Adjust opacity based on slider
                opacity = int(color[3] * self.opacity_var.get() / 100)
                overlay_array[mask] = (*color[:3], opacity)

            overlay = Image.fromarray(overlay_array, 'RGBA')

            # Composite with original image
            display_image = display_image.convert('RGBA')
            display_image = Image.alpha_composite(display_image, overlay)
            display_image = display_image.convert('RGB')

        # Convert to PhotoImage
        self.photo = ImageTk.PhotoImage(display_image)

        # Update canvas
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        self.canvas.config(scrollregion=(0, 0, display_image.width, display_image.height))

    def on_mouse_down(self, event):
        """Handle mouse button press."""
        self.drawing = True
        self.last_x = event.x
        self.last_y = event.y
        self.draw_at(event.x, event.y)

    def on_mouse_drag(self, event):
        """Handle mouse drag."""
        if self.drawing:
            # Draw line from last position to current
            self.draw_line(self.last_x, self.last_y, event.x, event.y)
            self.last_x = event.x
            self.last_y = event.y

    def on_mouse_up(self, event):
        """Handle mouse button release."""
        self.drawing = False

    def draw_at(self, x: int, y: int):
        """Draw at the given canvas coordinates."""
        if self.working_mask is None:
            return

        h, w = self.working_mask.shape
        if x < 0 or x >= w or y < 0 or y >= h:
            return

        # Create circular brush
        y_coords, x_coords = np.ogrid[:h, :w]
        mask = ((x_coords - x) ** 2 + (y_coords - y) ** 2) <= (self.brush_size / 2) ** 2

        # Apply brush
        self.working_mask[mask] = self.current_class

        self.update_display()

    def draw_line(self, x0: int, y0: int, x1: int, y1: int):
        """Draw line between two points (for smooth brush strokes)."""
        # Bresenham's line algorithm with circular brush
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        x, y = x0, y0

        while True:
            self.draw_at(x, y)

            if x == x1 and y == y1:
                break

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    def reset_to_prediction(self):
        """Reset current area under brush to original prediction (eraser)."""
        if self.original_mask is not None:
            self.working_mask = self.original_mask.copy()
            self.update_display()
            print("Reset to model prediction")

    def reset_mask(self):
        """Reset entire mask to blank or prediction."""
        if self.original_mask is not None:
            self.working_mask = self.original_mask.copy()
        else:
            h, w = self.current_image.size[1], self.current_image.size[0]
            self.working_mask = np.zeros((h, w), dtype=np.uint8)
        self.update_display()
        print("Reset mask")

    def save_annotation(self):
        """Save current annotation."""
        if self.working_mask is None or self.current_tile is None:
            return

        # Copy tile to images dir
        image_dest = self.images_dir / self.current_tile.name
        if not image_dest.exists():
            self.current_image.save(image_dest)

        # Save mask
        mask_dest = self.masks_dir / f"{self.current_tile.stem}_mask.png"
        mask_img = Image.fromarray(self.working_mask.astype(np.uint8), mode='L')
        mask_img.save(mask_dest)

        # Update progress
        tile_name = self.current_tile.name
        if tile_name not in self.progress['annotated']:
            self.progress['annotated'].append(tile_name)
        self.progress['last_modified'][tile_name] = datetime.now().isoformat()
        self.save_progress()

        print(f"Saved annotation: {mask_dest.name}")
        messagebox.showinfo("Saved", f"Annotation saved:\n{mask_dest.name}")

        # Auto-advance to next tile
        self.next_tile()

    def next_tile(self):
        """Load next tile."""
        if self.current_index < len(self.tiles) - 1:
            self.load_tile(self.current_index + 1)
        else:
            messagebox.showinfo("End", "Reached last tile")

    def prev_tile(self):
        """Load previous tile."""
        if self.current_index > 0:
            self.load_tile(self.current_index - 1)
        else:
            messagebox.showinfo("Start", "Already at first tile")

    def goto_tile(self):
        """Open dialog to jump to specific tile."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Go to Tile")
        dialog.geometry("300x150")

        ttk.Label(dialog, text=f"Enter tile number (1-{len(self.tiles)}):").pack(pady=10)

        entry = ttk.Entry(dialog)
        entry.pack(pady=5)
        entry.insert(0, str(self.current_index + 1))
        entry.focus()

        def go():
            try:
                index = int(entry.get()) - 1
                if 0 <= index < len(self.tiles):
                    self.load_tile(index)
                    dialog.destroy()
                else:
                    messagebox.showerror("Error", f"Invalid tile number. Must be 1-{len(self.tiles)}")
            except ValueError:
                messagebox.showerror("Error", "Please enter a valid number")

        ttk.Button(dialog, text="Go", command=go).pack(pady=10)
        entry.bind('<Return>', lambda e: go())

    def on_key_press(self, event):
        """Handle keyboard shortcuts."""
        key = event.char.lower()

        # Class selection (1-5)
        if key in '12345':
            class_id = int(key) - 1
            if class_id in CLASSES:
                self.set_class(class_id)

        # Navigation
        elif key == 'a':
            self.prev_tile()
        elif key == 'd':
            self.next_tile()

        # Actions
        elif key == 's':
            self.save_annotation()
        elif key == 'e':
            self.reset_to_prediction()
        elif key == 'm':
            self.show_mask_var.set(not self.show_mask_var.get())
            self.update_display()
        elif key == 'q':
            self.on_closing()

    def on_closing(self):
        """Handle window close."""
        if messagebox.askokcancel("Quit", "Are you sure you want to quit?"):
            self.save_progress()
            self.root.destroy()

    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(
        description='Interactive annotation helper for historical map tiles'
    )

    parser.add_argument(
        '--tiles-dir',
        required=True,
        help='Directory containing tile images to annotate'
    )

    parser.add_argument(
        '--output-dir',
        required=True,
        help='Directory to save annotations (will create images/ and masks/ subdirs)'
    )

    parser.add_argument(
        '--model',
        help='Path to trained model checkpoint (optional, for initial predictions)'
    )

    args = parser.parse_args()

    # Validate inputs
    tiles_dir = Path(args.tiles_dir)
    if not tiles_dir.exists():
        print(f"Error: Tiles directory does not exist: {tiles_dir}")
        sys.exit(1)

    if args.model and not Path(args.model).exists():
        print(f"Warning: Model file not found: {args.model}")
        print("Starting without model (blank masks)")
        args.model = None

    # Create and run annotation helper
    try:
        helper = AnnotationHelper(
            tiles_dir=args.tiles_dir,
            output_dir=args.output_dir,
            model_path=args.model
        )
        helper.run()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

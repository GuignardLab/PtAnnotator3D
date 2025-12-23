"""Point Annotator for large-scale 3D OME-TIF files."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import napari.viewer
import csv
import os
from pathlib import Path
from magicgui.widgets import FileEdit, RangeSlider, SpinBox
import numpy as np
import napari
from napari.utils.notifications import show_warning
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QAbstractSpinBox,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QLabel,
)
from tifffile import imread
import zarr

VALID_IMAGE_FORMATS = [".tif"]


class PtAnnotator3DWidget(QWidget):
    def __init__(self, napari_viewer: napari.viewer.Viewer):
        """Point Annotator Widget for 3D OME-TIF files."""
        super().__init__()
        self.viewer: napari.viewer.Viewer = napari_viewer
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.data = None
        self.shape = None
        self.datafile = FileEdit()
        self.datafile._list[-1].text = "Select Data File..."
        self.datafile.changed.connect(self.load_data)
        layout.addWidget(self.datafile.native)

        self.csv_points = None
        self.csvfile = FileEdit(mode="w", filter="*.csv")
        self.csvfile._list[-1].text = "Select CSV File..."
        self.csvfile.changed.connect(self.load_csv)
        layout.addWidget(self.csvfile.native)
        layout.addSpacerItem(QSpacerItem(10, 10))

        channel_layout = QHBoxLayout()
        channel_label = QLabel("Channel:")
        self.channel = SpinBox(min=0, max=0)
        self.channel.native.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum
        )
        channel_layout.addWidget(channel_label)
        channel_layout.addWidget(self.channel.native)
        layout.addLayout(channel_layout)
        layout.addSpacerItem(QSpacerItem(10, 10))
        self.g = self.generator(channel=self.channel.value)

        contrast_limits_layout = QHBoxLayout()
        contrast_limits_label = QLabel("Contrast Limits:")
        self.contrast_limits = RangeSlider(min=0, max=10_000)
        self.contrast_limits.native.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum
        )
        self.contrast_limits.changed.connect(self._update_live_contrast)
        contrast_limits_layout.addWidget(contrast_limits_label)
        contrast_limits_layout.addWidget(self.contrast_limits.native)
        layout.addLayout(contrast_limits_layout)
        layout.addSpacerItem(QSpacerItem(10, 10))

        chunk_shape_layout_wrapper = QVBoxLayout()
        chunk_shape_layout_wrapper.addWidget(
            QLabel("Chunk Shape"), alignment=Qt.AlignCenter
        )
        chunk_shape_layout_wrapper.setAlignment(Qt.AlignCenter)
        chunk_shape_layout = QHBoxLayout()
        self.chunk_spins = [
            SpinBox(min=0, max=0),
            SpinBox(min=0, max=0),
            SpinBox(min=0, max=0),
        ]
        for spin in self.chunk_spins:
            chunk_shape_layout.addWidget(spin.native)
            spin.native.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            spin.native.setButtonSymbols(QAbstractSpinBox.NoButtons)
        chunk_shape_layout_wrapper.addLayout(chunk_shape_layout)
        layout.addLayout(chunk_shape_layout_wrapper)
        layout.addSpacerItem(QSpacerItem(10, 10))

        confirm_button = QPushButton("Add new image (0)")
        confirm_button.clicked.connect(self.confirm)
        layout.addWidget(confirm_button)

        self.viewer.bind_key("0")(self.confirm)

        self.offset = (0, 0, 0)
        self.img_layer = None
        self.csv_layer = None
        self.points_layer = None

    @property
    def chunk_shape(self):
        return tuple([spin.value for spin in self.chunk_spins])

    def load_csv(self):
        """Loads the csv points list using the FileEdit dialog box."""
        if str(self.csvfile.value)[-4:] == ".csv":
            self.csv_points = self._load_csv(self.csvfile.value)

    def load_data(self):
        """Loads the data and corresponding metadata using the FileEdit dialogbox."""
        if str(self.datafile.value)[-4:] not in VALID_IMAGE_FORMATS:
            return
        store = imread(self.datafile.value, aszarr=True)
        self.data = zarr.open(store, mode="r")
        self.shape = self.data.shape
        if len(self.shape) == 3:
            self.channel.max = -1
            for e, spin in enumerate(self.chunk_spins):
                spin.max = self.data.shape[e]
        else:
            self.channel.max = self.data.shape[0] - 1
            for e, spin in enumerate(self.chunk_spins, start=1):
                spin.max = self.data.shape[e]

    def _load_csv(self, filename: str | Path):
        """Create or load a csv designed to store point data for napari.

        Parameters
        ----------
        filename : str or pathlib.Path
            Path to the csv file.

        Returns
        -------
        csv_points : list of lists
            List of point coordinates (point id excluded).
        """
        if not os.path.exists(filename):
            with open(filename, "w") as fp:
                fp.write("index,axis-0,axis-1,axis-2")

        with open(filename, "r") as csvfile:
            csv_points = [line for line in csv.reader(csvfile)][1:]
            csv_points = [[float(i) for i in line[1:]] for line in csv_points]
        return csv_points

    def _update_live_contrast(self):
        """Connect widget contrast limits to chunk image layer controls."""
        if self.img_layer is not None:
            self.img_layer.contrast_limits = self.contrast_limits.value

    def generator(self, channel):
        """Generator of chunks and points. Selects random coordinates.

        Parameters
        ----------
        channel : int
            Index of channel of the file to slice through.

        Yields
        -------
        chunk : numpy.ndarray
            Generated slice of the image.
        points : list
            List of points already saved in the chunk.
        """
        while True:  # maybe I can make this better than random?? not sure yet
            dx, dz, dy = self.chunk_shape
            xm, ym, zm = self.shape[1:]
            self.offset = (
                np.random.randint(xm - dx),
                np.random.randint(ym - dy),
                np.random.randint(zm - dz),
            )
            x, y, z = self.offset
            self.points = [
                (px, py, pz)
                for (px, py, pz) in self.csv_points
                if (x < px < x + dx)
                and (y < py < y + dy)
                and (z < pz < z + dz)
            ]
            if self.channel.value == -1:
                chunk = np.array(
                    self.data[x : x + dx, y : y + dy, z : z + dz]
                )
            else:
                chunk = np.array(
                    self.data[channel, x : x + dx, y : y + dy, z : z + dz]
                )
            yield chunk, self.points

    def confirm(self, napari_viewer):
        if not napari_viewer:
            napari_viewer = self.viewer
        if self.data is None or self.csv_points is None:
            show_warning(
                "Please select an input data file and an output csv file before trying to load chunks."
            )
            return
        if np.prod(self.chunk_shape) == 0:
            show_warning("Please select a valid chunk shape.")
            return
        if self.csv_layer in napari_viewer.layers:
            with open(self.csvfile.value, "w") as fp:
                writer = csv.writer(fp, lineterminator="\r")
                ox, oy, oz = self.offset
                self.csv_points = self.csv_points + [
                    [np.round(x) + ox, np.round(y) + oy, np.round(z) + oz]
                    for (x, y, z) in self.points_layer.data
                ]
                writer.writerows(
                    [["index", "axis-0", "axis-1", "axis-2"]]
                    + [
                        [i, x, y, z]
                        for i, (x, y, z) in enumerate(self.csv_points)
                    ]
                )
            del napari_viewer.layers[
                napari_viewer.layers.index(self.img_layer)
            ]
            del napari_viewer.layers[
                napari_viewer.layers.index(self.csv_layer)
            ]
            del napari_viewer.layers[
                napari_viewer.layers.index(self.points_layer)
            ]
        arr, points = next(self.g)
        self.img_layer = napari_viewer.add_image(arr, name="Chunk")
        self.img_layer.contrast_limits = self.contrast_limits.value
        self.csv_layer = napari_viewer.add_points(
            points, name=f"From CSV ({len(points)} points)", size=1
        )
        self.points_layer = napari_viewer.add_points(
            [], name="New Points", ndim=3, size=1
        )

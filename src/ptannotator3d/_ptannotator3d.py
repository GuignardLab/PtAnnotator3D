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
from napari.layers.utils._link_layers import link_layers
from napari.qt.threading import thread_worker
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
from skimage.io import imread, imsave
import zarr

VALID_IMAGE_FORMATS = [".tif", ".tiff"]

BOX_PATHS = np.array([
    [0,0,0],
    [1,0,0],
    [1,1,0],
    [0,1,0],
    [0,0,0],
    [0,0,1],
    [1,0,1],
    [1,1,1],
    [0,1,1],
    [0,0,1],
    [0,0,0],
    [1,0,0],
    [1,0,1],
    [1,1,1],
    [1,1,0],
    [0,1,0],
    [0,1,1]
])

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
        self.channel.changed.connect(lambda : setattr(self, "g", self.generator(self.channel.value, self.channel_coloc.value)))
        channel_layout.addWidget(channel_label)
        channel_layout.addWidget(self.channel.native)
        layout.addLayout(channel_layout)
        layout.addSpacerItem(QSpacerItem(10, 10))

        channel_coloc_layout = QHBoxLayout()
        channel_coloc_label = QLabel("Channel (colocalisation):")
        self.channel_coloc = SpinBox(min=0, max=0)
        self.channel_coloc.native.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum
        )
        self.channel_coloc.changed.connect(lambda : setattr(self, "g", self.generator(self.channel.value, self.channel_coloc.value)))
        channel_coloc_layout.addWidget(channel_coloc_label)
        channel_coloc_layout.addWidget(self.channel_coloc.native)
        layout.addLayout(channel_coloc_layout)
        layout.addSpacerItem(QSpacerItem(10, 10))

        self.g = self.generator(self.channel.value, self.channel_coloc.value)

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


        point_proj_layout_wrapper = QVBoxLayout()
        point_proj_layout_wrapper.addWidget(
            QLabel("Point Projection"), alignment=Qt.AlignCenter
        )
        point_proj_layout_wrapper.setAlignment(Qt.AlignCenter)
        point_proj_layout = QHBoxLayout()
        self.proj_spins = [
            SpinBox(min=0, max=100),
            SpinBox(min=0, max=100),
            SpinBox(min=0, max=100),
        ]
        for spin in self.proj_spins:
            point_proj_layout.addWidget(spin.native)
            spin.native.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            spin.native.setButtonSymbols(QAbstractSpinBox.NoButtons)
            spin.changed.connect(self._update_point_projections)
        point_proj_layout_wrapper.addLayout(point_proj_layout)
        layout.addLayout(point_proj_layout_wrapper)
        layout.addSpacerItem(QSpacerItem(10, 10))

        confirm_button = QPushButton("Add new image (Alt-0)")
        confirm_button.clicked.connect(self.confirm)
        layout.addWidget(confirm_button)

        self.save_path = FileEdit(mode="d")
        self.save_path._list[-1].text = "Select Save Folder..."
        layout.addWidget(self.save_path.native)
        save_chunk_button = QPushButton("Save chunk (Alt-1)")
        save_chunk_button.clicked.connect(self.save_chunk)
        layout.addWidget(save_chunk_button)

        self.viewer.bind_key("Alt-0")(self.confirm)
        self.viewer.bind_key("Alt-1")(self.save_chunk)
        self.viewer.bind_key("C")(self.toggle_coloc_visibility)

        self.offset = (0, 0, 0)
        self.img_layer = None
        self.co_layer = None
        self.chunk_after = None
        self.chunk_before = None
        self.csv_layer = None
        self.points_layer = None
        self.no_channels = False
        self._chunk_shape = None
        self.tmp = None

    @property
    def image_layers(self):
        return [self.img_layer, self.chunk_after, self.chunk_before]

    @property
    def bboxes_filename(self):
        return str(self.csvfile.value)[:-4]+"_bboxes.csv"

    @property
    def chunk_shape(self):
        if self._chunk_shape is None:
            self._chunk_shape = tuple([spin.value for spin in self.chunk_spins])
        return self._chunk_shape

    @property
    def projections(self):
        return tuple([spin.value for spin in self.proj_spins])

    @property
    def settings(self):
        return (self.channel, self.channel_coloc, self.chunk_shape)

    def load_csv(self):
        """Loads the csv points list using the FileEdit dialog box."""
        if str(self.csvfile.value)[-4:] == ".csv":
            self.csv_points = self._load_csv(self.csvfile.value)
            if not os.path.exists(self.bboxes_filename):
                with open(self.bboxes_filename, "w") as fp:
                    fp.write("index,shape-type,vertex-index,axis-0,axis-1,axis-2\n")                

    def load_data(self):
        """Loads the data and corresponding metadata using the FileEdit dialogbox."""
        if str(self.datafile.value)[-4:] not in VALID_IMAGE_FORMATS:
            return
        store = imread(self.datafile.value, aszarr=True)
        self.data = zarr.open(store, mode="r")
        self.shape = self.data.shape
        if len(self.shape) == 3:
            self.no_channels = True
            for e, spin in enumerate(self.chunk_spins):
                spin.max = self.data.shape[e]
        else:
            self.channel_coloc.max = self.data.shape[0] - 1
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
            self.chunk_after.contrast_limits = self.contrast_limits.value
            self.chunk_before.contrast_limits = self.contrast_limits.value

    def _update_point_projections(self):
        self.viewer.dims.margin_left = self.projections
        self.viewer.dims.margin_right = self.projections

    def _generate_bbox_export(self, idx):
        ox, oy, oz = self.offset
        dx, dy, dz = self.offset
        vertices = self.offset+BOX_PATHS*self._chunk_shape
        return [[idx, "path", e, vx, vy, vz] for e, (vx, vy, vz) in enumerate(vertices)]

    def toggle_coloc_visibility(self, napari_viewer):
        if not napari_viewer:
            napari_viewer = self.viewer
        if not hasattr(self, "co_layer") or self.co_layer is None:
            return
        self.co_layer.visible = not self.co_layer.visible

    def generator(self, channel, channel_coloc):
        """Generator of chunks and points. Selects random coordinates.

        Parameters
        ----------
        channel : int
            Index of channel of the file to slice through.
        channel_coloc : int
            Index of channel of the file to help colocalise (ignored if same as channel).

        Yields
        -------
        chunk : numpy.ndarray
            Generated slice of the image's main channel.
        chunk_coloc : numpy.ndarray
            Generated slice of the image's secondary channel.
        points : list
            List of points already saved in the chunk.
        """
        while True:  # maybe I can make this better than random?? not sure yet
            dx, dz, dy = self.chunk_shape
            xm, ym, zm = self.shape if self.no_channels else self.shape[1:4]
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
            if self.no_channels:
                chunk = np.array(
                    self.data[x : x + dx, y : y + dy, z : z + dz]
                )
                chunk_coloc = None
            else:
                chunk = np.array(
                    self.data[channel, x : x + dx, y : y + dy, z : z + dz]
                )
                chunk_coloc = np.array(
                    self.data[channel_coloc, x : x + dx, y : y + dy, z : z + dz]
                ) if channel != channel_coloc else None
            yield chunk, chunk_coloc, self.points


    @thread_worker(progress=True, start_thread=True)
    def _prepare_next_batch(self):
        self.tmp = next(self.g)

    def _prepare_backup(self):
        if self.points_layer is not None:
            self.backup = {
                "points_layer.data":self.points_layer.data,
                "offset":self.offset,
                "settings":self.settings
            }

    def confirm(self, napari_viewer):
        if not napari_viewer:
            napari_viewer = self.viewer
        if self.data is None or self.csv_points is None:
            show_warning(
                "Please select an input data file and an output csv file before trying to load chunks."
            )
            return
        if np.prod([spin.value for spin in self.chunk_spins]) == 0:
            show_warning("Please select a valid chunk shape.")
            return
        self._prepare_backup()
        if self.csv_layer in napari_viewer.layers:
            for layer in self.image_layers + [self.csv_layer, self.points_layer]:
                del napari_viewer.layers[
                    napari_viewer.layers.index(layer)
                ]
            if self.co_layer is not None:
                del napari_viewer.layers[
                    napari_viewer.layers.index(self.co_layer)
                ]
                self.co_layer = None
            self.save_and_update()
        self._chunk_shape = None
        if self.tmp is not None and self.settings == self.backup["settings"]:
            arr, co_arr, points = self.tmp
        else:
            arr, co_arr, points = next(self.g)
        self.tmp = None
        self.img_layer = napari_viewer.add_image(arr, name="Chunk", projection_mode="none")
        self.chunk_after = napari_viewer.add_image(np.array(list(arr[1:]) + [np.zeros_like(arr[0])]), name="Chunk (+1)", colormap="red", blending="additive", opacity=.5, projection_mode="none")
        self.chunk_before = napari_viewer.add_image(np.array([np.zeros_like(arr[0])] + list(arr[:-1])), name="Chunk (-1)", colormap="cyan", blending="additive", opacity=.5, projection_mode="none")
        for layer in self.image_layers:
            layer.contrast_limits = self.contrast_limits.value
        link_layers(self.image_layers, ["contrast_limits"])
        link_layers([self.chunk_after, self.chunk_before], ["visible"])
        if co_arr is not None:
            self.co_layer = napari_viewer.add_image(co_arr, name="Chunk (coloc)", projection_mode="none", colormap="magma", visible=False)

        self.csv_layer = napari_viewer.add_points(
            points, name=f"From CSV ({len(points)} points)", size=1
        )
        self.points_layer = napari_viewer.add_points(
            [], name="New Points", ndim=3, size=1
        )
        self._update_point_projections() # force recompute
        self._prepare_next_batch()

    @thread_worker(progress=True, start_thread=True)
    def save_and_update(self):
        with open(self.csvfile.value, "w") as fp:
            writer = csv.writer(fp, lineterminator="\r")
            ox, oy, oz = self.backup["offset"]
            self.csv_points = self.csv_points + [
                [np.round(x) + ox, np.round(y) + oy, np.round(z) + oz]
                for (x, y, z) in self.backup["points_layer.data"]
            ]
            writer.writerows(
                [["index", "axis-0", "axis-1", "axis-2"]]
                + [
                    [i, x, y, z]
                    for i, (x, y, z) in enumerate(self.csv_points)
                ]
            )
        with open(self.bboxes_filename, "r+") as fp:
            recent_chunk = list(fp.readlines())[-1]
            try:
                idx = int(recent_chunk[:recent_chunk.index(",")])+1
            except:
                idx = 0
            writer = csv.writer(fp, lineterminator="\n")
            writer.writerows(self._generate_bbox_export(idx))

    def save_chunk(self, napari_viewer):
        if not napari_viewer:
            napari_viewer = self.viewer
        fname = self.save_path.value.name
        files = [0]+[int(f[len(fname)+1:-4]) for f in os.listdir(self.save_path.value)]
        i = max(files)+1
        imsave(self.save_path.value/f"{fname}_{i:04d}.tif", self.img_layer.data)
        with open(self.save_path.value/f"{fname}_{i:04d}.csv", "w") as fp:
            writer = csv.writer(fp, lineterminator="\r")
            writer.writerows(
                [["axis-0", "axis-1", "axis-2"]]
                + [
                    [x, y, z]
                    for (x, y, z) in self.points_layer.data
                ]
            )

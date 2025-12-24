# Point Annotator 3D

A napari plugin streamlining manual point segmentation in napari on large 3D images (designed for data on a single time point).
The plugin is designed to synchronise changes to a chosen CSV file.

Chunks of a given shape, at random coordinates of the large image, are loaded in the napari viewer. 
You can then annotate points in the chunk and commit the changes to the selected CSV file. 
Points already detected in the chunk previously will be loaded from the CSV file, so you don't have to worry about repeat detections.

---

## Installation

To install :

    pip install git+https://github.com/GuignardLab/ptannotator3d.git

## Usage

- Open napari.
- Load the plugin into napari by clicking on `Plugins` in the toolbar and selecting `PtAnnotator 3D Widget`.

You will see this widget appear on the side of the viewer:

![](https://github.com/GuignardLab/ptannotator3d/blob/main/docs/widget.png)

From top to bottom:
- Select the image file. Selected formats currently only include TIF/TIFF files, I have yet to test other formats. If your image has time or channels, make sure it's the *first dimension* of your image (TXYZ or CXYZ).
- Select the CSV file to write to. You can also create a new file. If you just write the name of the file, it will write the file in the path from where napari is running, so be mindful of that.
  - Any CSV file that can be loaded into napari can also be loaded in. Therefore, if you have other algorithms that can detect points, it's then possible to save the points layer in napari as a CSV and open it again in this plugin.
- Select the channel / timepoint of the image to use. Auto-detects number of channels / timepoints. The plugin can also detect single timepoint + single channel images. 
  - The plugin is not built to handle images with both time and channels. If this is the dimensionality of your dataset, you should use a more sophisticated tool like [Mastodon](https://mastodon.readthedocs.io/en/latest/docs/partA/getting_started.html#getting-mastodon).
- Select contrast limits for all chunks to be loaded. This controller is synchronised to the image layers' contrast limits slider, but persists along chunks. 
  - You can still change the contrast limits of an individual layer using its layer controls, to fine tune the visuals for that layer, without changing this controller for future chunks. 
- Select the chunk shape. Each loaded chunk loaded will have this shape. It can of course be changed at any point during use of the plugin.
- Load a chunk by clicking on `Add new image (0)` or pressing `0` on a NumPad if you have one.


After clicking on the `Add new image (0)` for the first time, if all other settings are chosen correctly, three layers will be added to the viewer :

![](https://github.com/GuignardLab/ptannotator3d/blob/main/docs/layers.png)

- `Chunk` is an Image layer corresponding to the chunk of the image that was loaded.
- `From CSV (X points)` is a Points layer containing all the `X` points already present in the chunk according to the CSV selected in the settings. 
- `New Points` is an empty Points layer. It's the one the you should place points in.

Once you're satisfied with the points in the current chunk, commit them to the CSV by loading the next chunk. As the next chunk loads in, replacing these three layers, the points placed in `New Points` will be appended to the CSV, and will be visible in the `From CSV` layer if ever the area where they were placed is loaded again.

## Contributing

Contributions are very welcome. 

## License

Distributed under the terms of the [MIT] license,
"ptannotator3d" is free and open source software

## Issues

If you encounter any problems, please [file an issue](https://github.com/GuignardLab/ptannotator3d/issues) along with a detailed description.

---
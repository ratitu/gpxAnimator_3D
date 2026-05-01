# GPX Animator 3D

Streamlit web application that generates animated MP4 videos from GPX track files overlaid on 2D or 3D maps with optional photo integration.

## Features

- **2D/3D Map Visualization** - Render tracks on OpenStreetMap or Satellite basemaps with optional 3D terrain
- **Photo Integration** - Automatically overlay geotagged photos along the track using EXIF data
- **Customizable Animation** - Adjust FPS, video duration, resolution, and track color
- **Multiple Video Codecs** - Support for libx264, libx265, and libvpx
- **Track Statistics** - Display distance, elevation gain/loss, and duration
- **Follow Mode** - Camera follows the current position or shows full track overview
- **Mapbox Integration** - Optional 3D terrain visualization with Mapbox API

## Installation

```bash
pip install -r requirements.txt
```

### Requirements

- streamlit
- gpxpy
- staticmap
- moviepy
- Pillow
- numpy
- imageio-ffmpeg
- pydeck
- matplotlib
- scipy
- requests

## Usage

```bash
streamlit run app.py
```

1. **Upload GPX File** - Upload a GPX track file or use the default sample file
2. **Configure Settings** - Adjust animation parameters in the sidebar:
   - FPS and video duration
   - Map zoom level and resolution
   - Track color and follow mode
   - 3D terrain settings (requires Mapbox API key)
   - Video codec and quality
3. **Add Photos** - Upload geotagged photos (JPEG/PNG) with EXIF data
4. **Generate Video** - Click "Generate Video" and download the result

## Settings

### Animation
- **FPS**: 5-60 frames per second
- **Duration**: 5-120 seconds target video length
- **Resolution**: 480p, 720p, or 1080p

### Map
- **Basemap**: OpenStreetMap or Esri World Imagery (Satellite)
- **Zoom Level**: 1-20
- **Follow Mode**: Center camera on current track point

### 3D Terrain (Optional)
- Enable with Mapbox API key from https://account.mapbox.com/access-tokens/
- Adjust elevation exaggeration and camera pitch

### Video Output
- **Codec**: libx264 (default), libx265, or libvpx
- **Quality**: Low, Medium, High, or Ultra

## Sample Data

A sample GPX file (`bomJesusPerdoes.gpx`) is included for testing. The app automatically loads it if no file is uploaded.

## Video Output

Generated videos are encoded using ffmpeg (via imageio-ffmpeg) with the selected codec and quality preset. The default codec is libx264 with CRF-based quality control.

## Notes

- Photo matching uses timestamp (prioritizing GPS time) or GPS coordinates from EXIF data
- 3D rendering uses matplotlib with cubic interpolation for terrain surface
- Batch processing with threading for improved 2D rendering performance
- Requires ffmpeg installed on the system (provided by imageio-ffmpeg)

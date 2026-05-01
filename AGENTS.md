# gpxAnimator

Streamlit app that generates animated MP4 videos from GPX track files overlaid on maps.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Key Dependencies

- `streamlit` - Web UI framework
- `gpxpy` - GPX file parsing
- `staticmap` - Map tile rendering
- `moviepy` - Video generation (requires `imageio-ffmpeg` for codec)

## Notes

- Default basemap uses OpenStreetMap tiles (`http://a.tile.osm.org/{z}/{x}/{y}.png`)
- Satellite basemap uses Esri World Imagery
- A sample GPX file (`bomJesusPerdoes.gpx`) is included for testing
- Video codec: `libx264` (requires ffmpeg via `imageio-ffmpeg`)

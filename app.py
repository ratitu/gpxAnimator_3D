import streamlit as st
import gpxpy
import numpy as np
from staticmap import StaticMap, Line, CircleMarker
from moviepy import ImageSequenceClip
from PIL import Image, ExifTags
import tempfile
import os
import time
import io
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from scipy.interpolate import griddata

st.set_page_config(page_title="GPX Animator", layout="wide", page_icon="🗺️")

st.title("🗺️ GPX Map Video Animator")
st.markdown("Upload a GPX file and photos to generate an animated video of your track.")

# Sidebar Settings
st.sidebar.header("Animation Settings")
fps = st.sidebar.slider("Frames Per Second (FPS)", 5, 60, 24)
duration_target = st.sidebar.slider("Target Video Duration (seconds)", 5, 120, 15)
line_color = st.sidebar.color_picker("Track Color", "#FF0000")
zoom_level = st.sidebar.slider("Map Zoom Level", 1, 20, 14)
map_size = st.sidebar.selectbox("Video Resolution", [480, 720, 1080], index=1)
follow_mode = st.sidebar.checkbox("Follow Mode (Center on current point)", value=True)

# 3D Settings
st.sidebar.header("3D Map Settings")
mapbox_token = st.sidebar.text_input(
    "Mapbox API Key",
    value="",
    type="password",
    help="Get a free token at https://account.mapbox.com/access-tokens/",
)
use_3d = st.sidebar.checkbox("Enable 3D Terrain", value=True)
elevation_exaggeration = st.sidebar.slider("Elevation Exaggeration", 1.0, 10.0, 3.0) if use_3d else 1.0
pitch_3d = st.sidebar.slider("3D Camera Pitch (degrees)", 0, 75, 45) if use_3d else 0

# Video Output Settings
st.sidebar.header("Video Output")
video_codec = st.sidebar.selectbox("Codec", ["libx264", "libx265", "libvpx"], index=0)
video_quality = st.sidebar.select_slider(
    "Quality", ["Low", "Medium", "High", "Ultra"], value="High"
)
quality_presets = {"Low": 23, "Medium": 18, "High": 14, "Ultra": 8}
crf_value = quality_presets[video_quality]

# Basemap Selection
basemap_options = {
    "OpenStreetMap": "http://a.tile.osm.org/{z}/{x}/{y}.png",
    "Satellite (Esri World Imagery)": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
}
selected_basemap = st.sidebar.selectbox("Basemap", list(basemap_options.keys()))
map_url = basemap_options[selected_basemap]

# Photo Settings
st.sidebar.header("Photo Settings")
photo_display_duration = st.sidebar.slider("Photo Display Duration (seconds)", 1, 10, 3)

uploaded_file = st.file_uploader("Choose a GPX file", type=["gpx"])
uploaded_photos = st.file_uploader(
    "Upload Photos (with EXIF info)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

# Fallback to local file if it exists and no file is uploaded
default_gpx = "bomJesusPerdoes.gpx"
if uploaded_file is None and os.path.exists(default_gpx):
    st.info(f"Using default GPX file: {default_gpx}")
    with open(default_gpx, "rb") as f:
        gpx_data = f.read()
        uploaded_file = io.BytesIO(gpx_data)


def get_exif_data(image):
    """Extract EXIF data from an image."""
    exif_data = {}
    try:
        info = image._getexif()
        if info:
            for tag, value in info.items():
                decoded = ExifTags.TAGS.get(tag, tag)
                exif_data[decoded] = value
    except Exception:
        pass
    return exif_data


def get_decimal_from_dms(dms, ref):
    """Convert DMS (Degrees, Minutes, Seconds) to decimal degrees."""
    try:
        degrees = float(dms[0])
        minutes = float(dms[1])
        seconds = float(dms[2])

        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if ref in ["S", "W"]:
            decimal = -decimal
        return decimal
    except (TypeError, IndexError, ValueError):
        return None


def get_lat_lon(exif_data):
    """Extract latitude and longitude from EXIF data."""
    lat = None
    lon = None

    if "GPSInfo" in exif_data:
        gps_info = exif_data["GPSInfo"]

        gps_lat = gps_info.get(2)
        gps_lat_ref = gps_info.get(1)
        gps_lon = gps_info.get(4)
        gps_lon_ref = gps_info.get(3)

        if gps_lat and gps_lat_ref and gps_lon and gps_lon_ref:
            lat = get_decimal_from_dms(gps_lat, gps_lat_ref)
            lon = get_decimal_from_dms(gps_lon, gps_lon_ref)

    return lat, lon


def get_photo_timestamp(exif_data):
    """Extract timestamp from EXIF data, prioritizing GPS time."""
    if "GPSInfo" in exif_data:
        gps_info = exif_data["GPSInfo"]
        gps_time = gps_info.get(7)
        gps_date = gps_info.get(29)
        if gps_time and gps_date:
            try:
                if isinstance(gps_date, bytes):
                    gps_date = gps_date.decode("utf-8")
                h = float(gps_time[0])
                m = float(gps_time[1])
                s = float(gps_time[2])
                dt_str = f"{gps_date} {int(h):02d}:{int(m):02d}:{int(s):02d}"
                return datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
            except (ValueError, TypeError, IndexError):
                pass

    timestamp_str = exif_data.get("DateTimeOriginal") or exif_data.get("DateTime")
    if timestamp_str:
        if isinstance(timestamp_str, bytes):
            timestamp_str = timestamp_str.decode("utf-8")
        try:
            return datetime.strptime(timestamp_str, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            pass
    return None


def process_photos(photos, gpx_points):
    processed = []
    if not gpx_points:
        return []

    for uploaded_photo in photos:
        try:
            image_bytes = uploaded_photo.getvalue()
            image = Image.open(io.BytesIO(image_bytes))
            if image.mode != "RGB":
                image = image.convert("RGB")
            image_array = np.array(image)
            exif = get_exif_data(image)
            lat, lon = get_lat_lon(exif)
            ts = get_photo_timestamp(exif)

            if ts or (lat is not None and lon is not None):
                processed.append(
                    {
                        "image": image_array,
                        "timestamp": ts,
                        "lat": lat,
                        "lon": lon,
                        "name": uploaded_photo.name,
                    }
                )
        except Exception as e:
            st.sidebar.error(f"Error processing {uploaded_photo.name}: {e}")
    return processed


def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in kilometers."""
    from math import radians, sin, cos, sqrt, atan2

    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def parse_gpx(file):
    if hasattr(file, "getvalue"):
        gpx = gpxpy.parse(file.getvalue().decode("utf-8"))
    else:
        gpx = gpxpy.parse(file)
    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                points.append(
                    {
                        "lon": point.longitude,
                        "lat": point.latitude,
                        "time": point.time,
                        "elevation": point.elevation,
                    }
                )
    return points, gpx


def get_track_stats(points):
    """Calculate track statistics."""
    if not points or len(points) < 2:
        return None

    total_distance = 0.0
    elevation_gain = 0.0
    elevation_loss = 0.0

    for i in range(1, len(points)):
        prev = points[i - 1]
        curr = points[i]
        total_distance += haversine(prev["lat"], prev["lon"], curr["lat"], curr["lon"])

        if prev["elevation"] is not None and curr["elevation"] is not None:
            elev_diff = curr["elevation"] - prev["elevation"]
            if elev_diff > 0:
                elevation_gain += elev_diff
            else:
                elevation_loss += abs(elev_diff)

    times = [p["time"] for p in points if p["time"] is not None]
    duration = None
    if len(times) >= 2:
        duration = (times[-1] - times[0]).total_seconds()

    return {
        "distance_km": total_distance,
        "distance_mi": total_distance * 0.621371,
        "elevation_gain_m": elevation_gain,
        "elevation_loss_m": elevation_loss,
        "duration_sec": duration,
        "num_points": len(points),
    }


def create_3d_preview(points, mapbox_token, use_3d, elevation_exaggeration, pitch_3d):
    """Create a 3D preview using pydeck."""
    import pydeck as pdk

    if not mapbox_token:
        st.warning("Enter a Mapbox API Key in the sidebar to enable 3D preview.")
        return

    lons = [p["lon"] for p in points]
    lats = [p["lat"] for p in points]
    elevs = [p["elevation"] if p["elevation"] is not None else 0 for p in points]

    track_data = [
        {"lon": lon, "lat": lat, "elevation": elev}
        for lon, lat, elev in zip(lons, lats, elevs)
    ]

    center_lon = np.mean(lons)
    center_lat = np.mean(lats)

    layers = [
        pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": [lons[0], lats[0]]}, {"position": [lons[-1], lats[-1]]}],
            get_position="position",
            get_fill_color=[0, 255, 0, 255],
            get_radius=50,
        ),
        pdk.Layer(
            "PathLayer",
            data={"path": [[lon, lat] for lon, lat in zip(lons, lats)]},
            get_path="path",
            get_color=[255, 0, 0, 255],
            get_width=5,
            width_units="pixels",
        ),
    ]

    if use_3d and elevation_exaggeration > 1:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=track_data,
                get_position=["lon", "lat"],
                get_fill_color=[255, 0, 0, 180],
                get_radius=30,
                get_elevation="elevation * " + str(elevation_exaggeration),
                elevation_units="meters",
            )
        )

    view_state = pdk.ViewState(
        longitude=center_lon,
        latitude=center_lat,
        zoom=zoom_level - 2,
        pitch=pitch_3d,
        bearing=0,
    )

    os.environ["MAPBOX_API_KEY"] = mapbox_token

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/satellite-streets-v12" if selected_basemap.startswith("Satellite") else "mapbox://styles/mapbox/streets-v12",
    )

    st.pydeck_chart(deck)


def download_tile(url_template, x, y, z):
    """Download a single map tile."""
    url = url_template.replace("{x}", str(x)).replace("{y}", str(y)).replace("{z}", str(z))
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code == 200:
            return Image.open(io.BytesIO(response.content))
    except Exception:
        pass
    return None


def lonlat_to_tile(lon, lat, zoom):
    """Convert longitude/latitude to tile coordinates."""
    import math
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def render_3d_frame(args):
    """Render a single 3D frame using matplotlib."""
    (
        i,
        anim_points,
        photos,
        photo_events,
        size,
        zoom,
        color,
        follow,
        url_template,
        center,
        elev_exag,
        pitch,
        current_view_point_idx,
    ) = args

    current_pt = anim_points[i]
    lons = [p["lon"] for p in anim_points]
    lats = [p["lat"] for p in anim_points]
    elevs = [p["elevation"] if p["elevation"] is not None else 0 for p in anim_points]

    min_elev = min(elevs)
    max_elev = max(elevs)
    elev_range = max_elev - min_elev if max_elev != min_elev else 1

    fig = plt.figure(figsize=(size / 100, size / 100), dpi=100)
    ax = fig.add_subplot(111, projection="3d")

    lat_range = max(lats) - min(lats)
    lon_range = max(lons) - min(lons)

    xs = np.array(lons)
    ys = np.array(lats)
    zs = np.array(elevs) * elev_exag

    xi = np.linspace(min(xs), max(xs), 100)
    yi = np.linspace(min(ys), max(ys), 100)
    xi_grid, yi_grid = np.meshgrid(xi, yi)
    zi_grid = griddata((xs, ys), zs, (xi_grid, yi_grid), method="cubic", fill_value=min(zs))

    try:
        tile_x, tile_y = lonlat_to_tile(current_pt["lon"], current_pt["lat"], zoom)
        tile_img = download_tile(url_template, tile_x, tile_y, zoom)
        if tile_img is not None:
            ax.plot_surface(
                xi_grid, yi_grid, zi_grid,
                facecolors=np.array(tile_img) / 255.0,
                rstride=1, cstride=1,
                alpha=0.8,
                shade=True,
            )
        else:
            ax.plot_surface(xi_grid, yi_grid, zi_grid, cmap="terrain", alpha=0.8)
    except Exception:
        ax.plot_surface(xi_grid, yi_grid, zi_grid, cmap="terrain", alpha=0.8)

    current_track_x = [p["lon"] for p in anim_points[: i + 1]]
    current_track_y = [p["lat"] for p in anim_points[: i + 1]]
    current_track_z = [p["elevation"] * elev_exag if p["elevation"] is not None else 0 for p in anim_points[: i + 1]]

    ax.plot(current_track_x, current_track_y, current_track_z, color=color, linewidth=3)

    ax.scatter(
        [current_pt["lon"]],
        [current_pt["lat"]],
        [current_pt["elevation"] * elev_exag if current_pt["elevation"] is not None else 0],
        color=color,
        s=100,
        marker="o",
    )

    for photo in photos:
        if photo["lat"] is not None and photo["lon"] is not None:
            ax.scatter(
                [photo["lon"]],
                [photo["lat"]],
                [0],
                color="yellow",
                s=50,
                marker="s",
            )

    if follow:
        ax.set_xlim(current_pt["lon"] - lon_range / 2, current_pt["lon"] + lon_range / 2)
        ax.set_ylim(current_pt["lat"] - lat_range / 2, current_pt["lat"] + lat_range / 2)
    else:
        ax.set_xlim(min(lons), max(lons))
        ax.set_ylim(min(lats), max(lats))

    ax.set_zlim(min(zs), max(zs))
    ax.view_init(elev=pitch, azim=0)
    ax.axis("off")

    fig.tight_layout(pad=0)
    fig.canvas.draw()

    image = np.frombuffer(fig.canvas.buffer_rgba(), dtype=np.uint8)
    image = image.reshape(fig.canvas.get_width_height()[::-1] + (4,))
    image = image[:, :, :3]
    plt.close(fig)

    active_candidates = []
    for event in photo_events:
        if event["start_frame"] <= i <= event["end_frame"]:
            dist = abs(i - event["target_frame"])
            active_candidates.append((dist, event["image"]))

    if active_candidates:
        active_candidates.sort(key=lambda x: x[0])
        _, best_photo_array = active_candidates[0]
        photo_img = Image.fromarray(best_photo_array)
        photo_img.thumbnail((size // 3, size // 3))
        border = 5
        framed_photo = Image.new(
            "RGB",
            (photo_img.width + 2 * border, photo_img.height + 2 * border),
            "white",
        )
        framed_photo.paste(photo_img, (border, border))

        final_img = Image.fromarray(image)
        final_img.paste(
            framed_photo,
            (size - framed_photo.width - 15, size - framed_photo.height - 15),
        )
        image = np.array(final_img)

    return i, image


def render_frame(args):
    """Render a single frame (for batch processing - 2D mode)."""
    (
        i,
        anim_points,
        photos,
        photo_events,
        size,
        zoom,
        color,
        follow,
        url_template,
        center,
    ) = args
    current_pt = anim_points[i]
    current_track = [(p["lon"], p["lat"]) for p in anim_points[: i + 1]]

    frame_map = StaticMap(size, size, url_template=url_template)

    for photo in photos:
        if photo["lat"] is not None and photo["lon"] is not None:
            coord = (photo["lon"], photo["lat"])
            frame_map.add_marker(CircleMarker(coord, "black", 12))
            frame_map.add_marker(CircleMarker(coord, "yellow", 8))

    if len(current_track) > 1:
        frame_map.add_line(Line(current_track, color, 3))

    frame_map.add_marker(
        CircleMarker((current_pt["lon"], current_pt["lat"]), "white", 10)
    )
    frame_map.add_marker(CircleMarker((current_pt["lon"], current_pt["lat"]), color, 6))

    if follow:
        image = frame_map.render(
            zoom=zoom, center=(current_pt["lon"], current_pt["lat"])
        )
    else:
        image = frame_map.render(zoom=zoom, center=center)

    active_candidates = []
    for event in photo_events:
        if event["start_frame"] <= i <= event["end_frame"]:
            dist = abs(i - event["target_frame"])
            active_candidates.append((dist, event["image"]))

    if active_candidates:
        active_candidates.sort(key=lambda x: x[0])
        _, best_photo_array = active_candidates[0]
        photo_img = Image.fromarray(best_photo_array)
        photo_img.thumbnail((size // 2.2, size // 2.2))
        border = 5
        framed_photo = Image.new(
            "RGB",
            (photo_img.width + 2 * border, photo_img.height + 2 * border),
            "white",
        )
        framed_photo.paste(photo_img, (border, border))
        image.paste(
            framed_photo,
            (size - framed_photo.width - 15, size - framed_photo.height - 15),
        )

    return i, np.array(image)


def create_animation(
    points,
    fps,
    duration,
    size,
    zoom,
    color,
    follow,
    url_template,
    photos,
    photo_dur,
    codec,
    crf,
    use_3d=False,
    elev_exag=1.0,
    pitch=45,
):
    total_frames = fps * duration
    if len(points) < 2:
        st.error("Not enough points in GPX file.")
        return None

    step = max(1, len(points) // total_frames)
    anim_points = points[::step]

    photo_events = []
    frames_to_show = int(fps * photo_dur)
    half_dur = frames_to_show // 2

    for photo in photos:
        best_frame_idx = -1

        if photo["timestamp"]:
            min_time_diff = float("inf")
            photo_ts = photo["timestamp"].replace(tzinfo=None)
            for i, pt in enumerate(anim_points):
                if pt["time"]:
                    diff = abs(
                        (pt["time"].replace(tzinfo=None) - photo_ts).total_seconds()
                    )
                    if diff < min_time_diff:
                        min_time_diff = diff
                        best_frame_idx = i
            if min_time_diff > 3600:
                best_frame_idx = -1

        if (
            best_frame_idx == -1
            and photo["lat"] is not None
            and photo["lon"] is not None
        ):
            min_dist = float("inf")
            for i, pt in enumerate(anim_points):
                dist = np.sqrt(
                    (photo["lat"] - pt["lat"]) ** 2 + (photo["lon"] - pt["lon"]) ** 2
                )
                if dist < min_dist:
                    min_dist = dist
                    best_frame_idx = i
            if min_dist > 0.005:
                best_frame_idx = -1

        if best_frame_idx != -1:
            photo_events.append(
                {
                    "target_frame": best_frame_idx,
                    "start_frame": max(0, best_frame_idx - half_dur),
                    "end_frame": best_frame_idx + half_dur,
                    "image": photo["image"],
                }
            )

    center = None
    if not follow:
        lons = [p["lon"] for p in points]
        lats = [p["lat"] for p in points]
        center = (np.mean(lons), np.mean(lats))

    frames = [None] * len(anim_points)
    batch_size = 20 if use_3d else 50
    num_batches = (len(anim_points) + batch_size - 1) // batch_size

    progress_bar = st.progress(0)
    status_text = st.empty()
    start_time = time.time()

    for batch_idx in range(num_batches):
        batch_start = batch_idx * batch_size
        batch_end = min(batch_start + batch_size, len(anim_points))

        if use_3d:
            args_list = [
                (
                    i,
                    anim_points,
                    photos,
                    photo_events,
                    size,
                    zoom,
                    color,
                    follow,
                    url_template,
                    center,
                    elev_exag,
                    pitch,
                    i,
                )
                for i in range(batch_start, batch_end)
            ]

            for args in args_list:
                idx, frame = render_3d_frame(args)
                frames[idx] = frame

                batch_progress = (batch_idx * batch_size + (idx - batch_start + 1)) / len(anim_points)
                elapsed = time.time() - start_time
                if batch_progress > 0:
                    eta = elapsed / batch_progress - elapsed
                    status_text.text(
                        f"Rendering frame {idx + 1}/{len(anim_points)}... ETA: {int(eta)}s"
                    )
                progress_bar.progress(min(batch_progress, 1.0))
        else:
            args_list = [
                (
                    i,
                    anim_points,
                    photos,
                    photo_events,
                    size,
                    zoom,
                    color,
                    follow,
                    url_template,
                    center,
                )
                for i in range(batch_start, batch_end)
            ]

            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(render_frame, args_list))

            for i, frame in results:
                frames[i] = frame

            batch_progress = batch_end / len(anim_points)
            elapsed = time.time() - start_time
            if batch_progress > 0:
                eta = elapsed / batch_progress - elapsed
                status_text.text(
                    f"Rendering frame {batch_end}/{len(anim_points)}... ETA: {int(eta)}s"
                )
            progress_bar.progress(min(batch_progress, 1.0))

    frames = [f for f in frames if f is not None]
    progress_bar.progress(1.0)
    status_text.text("Compiling video...")

    try:
        clip = ImageSequenceClip(frames, fps=fps)
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")

        ffmpeg_params = ["-preset", "medium"]
        if codec in ["libx264", "libx265"]:
            ffmpeg_params.extend(["-crf", str(crf)])

        clip.write_videofile(
            tmp_file.name,
            codec=codec,
            audio=False,
            logger=None,
            ffmpeg_params=ffmpeg_params,
        )
        return tmp_file.name
    except Exception as e:
        st.error(f"Error during video generation: {e}")
        return None


if uploaded_file is not None:
    try:
        file_key = getattr(uploaded_file, "name", default_gpx) + str(
            getattr(uploaded_file, "size", 0)
        )

        if (
            "gpx_cache" not in st.session_state
            or st.session_state.get("gpx_cache_key") != file_key
        ):
            points, gpx_data = parse_gpx(uploaded_file)
            st.session_state["gpx_cache"] = (points, gpx_data)
            st.session_state["gpx_cache_key"] = file_key
        else:
            points, gpx_data = st.session_state["gpx_cache"]

        st.success(f"Parsed {len(points)} GPS points.")

        has_time_data = any(p["time"] is not None for p in points)
        if not has_time_data:
            st.warning(
                "GPX file has no timestamp data. Animation will use uniform timing."
            )

        stats = get_track_stats(points)
        if stats:
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Distance", f"{stats['distance_km']:.2f} km")
            col2.metric("Distance", f"{stats['distance_mi']:.2f} mi")
            col3.metric("Elevation Gain", f"{stats['elevation_gain_m']:.0f} m")
            col4.metric("Elevation Loss", f"{stats['elevation_loss_m']:.0f} m")
            if stats["duration_sec"]:
                mins = int(stats["duration_sec"] // 60)
                secs = int(stats["duration_sec"] % 60)
                col5.metric("Duration", f"{mins}m {secs}s")
            else:
                col5.metric("Duration", "N/A")

        # 3D Preview
        if use_3d:
            st.subheader("3D Map Preview")
            create_3d_preview(points, mapbox_token, use_3d, elevation_exaggeration, pitch_3d)

        photos = []
        if uploaded_photos:
            with st.spinner("Processing photos..."):
                photos = process_photos(uploaded_photos, points)
                st.success(f"Successfully processed {len(photos)} photos.")

        if st.button("Generate Video"):
            start_time = time.time()
            with st.spinner("Generating animation..."):
                video_path = create_animation(
                    points,
                    fps,
                    duration_target,
                    map_size,
                    zoom_level,
                    line_color,
                    follow_mode,
                    map_url,
                    photos,
                    photo_display_duration,
                    video_codec,
                    crf_value,
                    use_3d=use_3d,
                    elev_exag=elevation_exaggeration,
                    pitch=pitch_3d,
                )

                if video_path:
                    st.video(video_path)
                    with open(video_path, "rb") as f:
                        st.download_button(
                            "Download Video", f, "gpx_animation.mp4", "video/mp4"
                        )
                    os.remove(video_path)
    except Exception as e:
        st.error(f"Error: {e}")
        st.exception(e)

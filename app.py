# /home/ubuntu/app.py
# APP.PY FOR SERVER DEPLOYMENT

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import logging
import rasterio
from rasterio.crs import CRS
from rasterio.errors import RasterioIOError
from pyproj import Transformer
from pyproj.exceptions import CRSError
import os # Import os to potentially help with paths if needed

# --- Basic Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')

# --- Initialize Flask App ---
app = Flask(__name__)
CORS(app) # Allow Cross-Origin Requests


def classify_flood_level(value):
    """Classifies the flood level based on raster value."""
    if value <= 0:
        return "No Flood"
    elif 0 < value <= 0.24:
        return "Low Flood Level"
    elif 0.25 <= value < 0.5:
        return "Moderate Flood Level"
    elif value >= 0.5:
        return "High Flood Level"
    else:
        # This case might indicate an issue or NoData if not handled explicitly
        return "Not in Scope"


# --- API Endpoint ---
# Changed route to include /api/ prefix
@app.route("/api/get-band1", methods=["POST"])
def get_band1_value():
    app.logger.info(f"Received request at /api/get-band1")

    try:
        data = request.get_json()
        if not data:
            app.logger.warning("No JSON data received.")
            return jsonify({"error": "Request must contain JSON data"}), 400

        # --- Validate incoming data keys ---
        required_keys = ["lng", "lat", "layerIndex"]
        if not all(key in data for key in required_keys):
             missing_keys = [key for key in required_keys if key not in data]
             app.logger.warning(f"Missing keys in JSON payload: {missing_keys}")
             return jsonify({"error": f"Missing required keys in request body: {', '.join(missing_keys)}"}), 400

        lng = data["lng"]
        lat = data["lat"]
        index = data["layerIndex"]  # Default to 1 if not provided
        app.logger.info(f"Processing coordinates: lng={lng}, lat={lat} and layerIndex={index}")

        TIF_FILE_PATH = f'./raster_data/original/tif_rgb_{index}.tif';  # Update this path as needed
        # Consider opening the dataset once at app startup for efficiency if the app
        # handles high traffic, but be mindful of Gunicorn workers.
        # Per-request opening is simpler to manage initially.
        with rasterio.open(TIF_FILE_PATH) as dataset:
            app.logger.debug(f"Opened dataset: {TIF_FILE_PATH}")
            target_crs = "EPSG:32651"
            app.logger.debug(f"Dataset CRS: {target_crs}")

            # # Transform coordinate to raster CRS if needed
            if target_crs != CRS.from_epsg(4326):
                app.logger.debug(f"Transforming coordinates from EPSG:4326 to {target_crs}")
                transformer = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
                x, y = transformer.transform(lng, lat)
                app.logger.debug(f"Transformed coordinates: x={x}, y={y}")
            else:
                x, y = lng, lat
                app.logger.debug(f"Using original coordinates (dataset is EPSG:4326): x={x}, y={y}")

            # app.logger.debug(f"Transformed coordinates: x={x}, y={y}")
            # Convert map coordinates to pixel row/col
            # Add error handling in case coordinates are outside bounds

            try:
                 row, col = dataset.index(x, y)
                 app.logger.debug(f"Raster index: row={row}, col={col}")
            except IndexError: # Catch out-of-bounds errors
                 app.logger.warning(f"Coordinates lng={lng}, lat={lat} (x={x}, y={y}) are outside raster bounds.")
                 return jsonify({
                      "error": "Coordinates are outside the raster file bounds",
                      "value": 0, # Indicate no valid value
                      "flood_level": "Outside Bounds"
                 }), 404 # Not Found status seems appropriate

            # Read Band 1 value at the given row/col
            # Ensure band index is correct (usually 1-based for dataset.read)
            band1 = dataset.read(1)
            value = band1[row, col]
            app.logger.info(f"Raw value at (row={row}, col={col}): {value}")

            # Classify the value
            flood_level = classify_flood_level(value)
            app.logger.info(f"Classified flood level: {flood_level}")

        # Prepare successful response
        response_data = {
            # Convert numpy types (like float32) to standard Python float for JSON
            "value": float(value) if value != -9999 else 0,
            "flood_level": flood_level,
            "row": row,
            "col": col,
            "message": "Band1 value retrieved successfully"
        }
        app.logger.info("Request processed successfully.")
        return jsonify(response_data), 200

    # Specific Error Handling
    except Exception as e:
        return jsonify({
            "value": 0,  # âœ… Convert to native float
            "flood_level": "Not in scope",
            "row": 0,
            "col": 0,
            "message": "Band1 value retrieved unsuccessfully",
            "error": str(e)})
        #return jsonify({"error": str(e)}), 500
    # except KeyError as e:
    #      app.logger.error(f"Missing key in JSON data: {e}", exc_info=True)
    #      return jsonify({"error": f"Missing expected data in request: {e}"}), 400 # Bad request
    # except (RasterioIOError, FileNotFoundError) as e:
    #      app.logger.error(f"Error opening or reading raster file '{TIF_FILE_PATH}': {e}", exc_info=True)
    #      return jsonify({"error": f"Could not access or read the raster data file."}), 500 # Server error
    # except CRSError as e:
    #      app.logger.error(f"Coordinate transformation error: {e}", exc_info=True)
    #      return jsonify({"error": "Error during coordinate system transformation."}), 600 # Server error
    # except Exception as e:
    #      # Catch-all for other unexpected errors
    #      app.logger.error(f"An unexpected error occurred: {e}", exc_info=True)
    #      return jsonify({"error": "An internal server error occurred."}), 700 # Server error


# --- Optional: Root Endpoint for Health Check ---
@app.route('/')
def index():
    return render_template("index.html")  

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/floodmap")
def floodmap():
    return render_template("floodmap.html")

@app.route("/report")
def report():
    return render_template("report.html")

# --- IMPORTANT: NO app.run() HERE ---
# Gunicorn will start the app via the systemd service.
if __name__ == "__main__":
    app.run(debug=True) # DO NOT USE THIS FOR PRODUCTION

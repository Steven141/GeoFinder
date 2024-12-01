import requests
import random
import os
import json
from geopy.geocoders import Nominatim
from googletrans import Translator
from PIL import Image
from io import BytesIO


NUM_IMAGES = 2
DENSITY_RADIUS = {
    "high": 1000,  # Urban areas
    "medium": 5000,  # Rural areas
    "low": 10000,  # Remote areas
}


def main():
    file_path = "API.txt"
    try:
        with open(file_path, "r") as file:
            api_key = file.read().strip()  # Strip removes extra whitespace or newlines
    except FileNotFoundError:
        print(f"Error: {file_path} not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    json_path = "bounding_boxes.json"
    try:
        with open(json_path, "r") as json_file:
            country_bounding_boxes = json.load(json_file)
    except FileNotFoundError:
        print(f"Error: {file_path} not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    image_id_to_cord = {}
    country_to_cords = {}

    for k, v in country_bounding_boxes.items():
        lat = random.uniform(v['min_lat'], v['max_lat'])
        lng = random.uniform(v['min_lng'], v['max_lng'])
        radius = DENSITY_RADIUS[v['density']]

        valid_coverage, data = check_street_view_coverage(lat, lng, radius, api_key)
        while not valid_coverage:
            print(f'invalid for: {k}, {lat}, {lng}\n')
            lat = random.uniform(v['min_lat'], v['max_lat'])
            lng = random.uniform(v['min_lng'], v['max_lng'])
            valid_coverage, data = check_street_view_coverage(lat, lng, radius, api_key)
        print(f'Expected = {k}, {lat}, {lng}')
        pano_id = data['pano_id']
        lat = data['location']['lat']
        lng = data['location']['lng']
        geolocator = Nominatim(user_agent="my-app")
        location = geolocator.reverse(f"{lat},{lng}")
        country = location.address.split(", ")[-1]
        translator = Translator()
        country = translator.translate(country, src='auto', dest='en').text

        print(f'Got Country = {country}, lat = {lat}, lng = {lng}, pano_id = {pano_id}')
    return

    while len(image_id_to_cord) < NUM_IMAGES:

        lat = random.uniform(-60, 70)
        lng = random.uniform(-180, 180)
        valid_coverage, data = check_street_view_coverage(lat, lng, api_key)
        if not valid_coverage:
            continue

        pano_id = data['pano_id']
        lat = data['location']['lat']
        lng = data['location']['lng']

        if pano_id in image_id_to_cord:
            continue

        geolocator = Nominatim(user_agent="my-app")
        location = geolocator.reverse(f"{lat},{lng}")
        country = location.address.split(", ")[-1]

        print(f'Country = {country}, lat = {lat}, lng = {lng}, pano_id = {pano_id}')

        image_id_to_cord[pano_id] = (lat, lng, country)

        tiles = []
        for heading in range(0, 360, 90):
            row_tiles = []
            for pitch in [0]:  # Adjust pitch for 3 rows
                tile = fetch_streetview_tile(api_key, lat, lng, heading, pitch)
                row_tiles.append(tile)
            tiles.append(row_tiles)
        stitched_image = stitch_tiles(tiles)
        stitched_image.save(f"data/{pano_id}.jpg")


def check_street_view_coverage(lat, lng, radius, api_key):
    """
    Check if Google Street View imagery exists for the given latitude and longitude.
    :param lat: Latitude.
    :param lng: Longitude.
    :return: True if imagery exists, False otherwise.
    """
    metadata_url = "https://maps.googleapis.com/maps/api/streetview/metadata"
    params = {
        "location": f"{lat},{lng}",
        'radius': radius,  # search radius in meters
        "key": api_key,
    }
    response = requests.get(metadata_url, params=params)
    data = response.json()

    if response.status_code == 200 and data["status"] == "OK":
        return True, data
    else:
        print(f"No Street View imagery for {lat}, {lng}: {data.get('status', 'Unknown error')}")
        return False, data


def stitch_tiles(tiles):
    rows = len(tiles[0])
    cols = len(tiles)
    tile_width, tile_height = tiles[0][0].size

    # Create a blank image canvas
    stitched_image = Image.new(
        "RGB", (cols * tile_width, rows * tile_height)
    )

    # Paste each tile into the correct position
    for col_idx, col in enumerate(tiles):
        for row_idx, tile in enumerate(col):
            stitched_image.paste(tile, (col_idx * tile_width, row_idx * tile_height))

    return stitched_image


def fetch_streetview_tile(api_key, lat, lng, heading=0, pitch=0, fov=90):
    base_url = "https://maps.googleapis.com/maps/api/streetview"
    params = {
        "size": "640x640",       # Image size
        "location": f"{lat},{lng}",
        "heading": heading,
        "pitch": pitch,
        "fov": fov,             # Field of View
        "key": api_key
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        print("Tile saved successfully!")
        return Image.open(BytesIO(response.content))
    else:
        print(f"Error fetching tile: {response.status_code} - {response.text}")
        return None


if __name__ == "__main__":
    main()
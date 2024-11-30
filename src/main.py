import requests
from PIL import Image
from io import BytesIO


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

    lat, lng = 48.858844, 2.294351
    tiles = []
    for heading in range(0, 360, 90):  # Fetch 3 tiles (0°, 120°, 240°)
        row_tiles = []
        for pitch in [0]:  # Adjust pitch for 3 rows
            tile = fetch_streetview_tile(api_key, lat, lng, heading, pitch)
            row_tiles.append(tile)
        tiles.append(row_tiles)
    stitched_image = stitch_tiles(tiles)
    stitched_image.save("stitched_streetview_3.jpg")


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
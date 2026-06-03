import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# ==========================================
# 1. CORE PIPELINE CONFIGURATION
# ==========================================

TARGET = 25
CHALLENGERS = 5
POOL_SIZE = TARGET + CHALLENGERS # 30

WINDOWS = {
    "soca": 4,         
    "dancehall": 4,     
    "afrobeats": 6,     
    "bouyon": 6         
}

BLACKLIST = ["mix", "dj", "set", "live", "radio", "intro", "roadmix"]
MAINSTREAM_BLACKLIST = ["drake", "don toliver", "chris brown", "justin bieber", "ed sheeran"]

PLAYLIST_QUERIES = {
    "dancehall": ["2026 dancehall", "new dancehall", "top dancehall"],
    "afrobeats": ["2026 afrobeats", "new afrobeats", "top afrobeats"]
}

# ==========================================
# 2. FIXED ARRAYS & EXCLUSIVE ID MAPS
# ==========================================

BOUYON_ARTIST_IDS = [
    "2eIEzwxBh1vDSSbUfZkeLL",
    "3Oc7o3kzzpLium0YxZPVri",
    "29DEO5ubNTmLbFSEZDP2we",
    "0mpZpEH8VcL0tYoGLhR8sd",
    "390GislU2lqdtKcuFMIvjK",
    "6bEej9F7Pkkto542i9mran",
    "1DpASCaDoS1AAKFHb6uldr",
    "5Zjgfa0fywmVbwc5dPlScR",
    "1DaLT7Mgy04h833FKXKGO0"
]

SOCA_ARTIST_IDS = [
    "6wxP7SSzfvi21Cnl8JicdQ",
    "7E6r9S8qCRfZVCjF1A8do6",
    "0crMctn4iXaE3XCHpeBkOt",
    "1K23l3n63BTCtIMm0TyS4c",
    "61buXyJGplh38VDpEaB2ds",
    "6nPHDCN7qmxO86eN1grP54",
    "4nLVEYSAcpANC0BV87P4rd",
    "5WYAHpwcYoSdCz5nXebrKn",
    "10AVFI86WCq4tNhY31g6FL",
    "1lE1SGLNabSpBbJB9A9qtU",
    "56BHYURgbka2nQbBy8XZ3x",
    "1qKzKUnuQsjB83hBZffoq0",
    "3uqI1IbL5XKd3Lf8FVSZWH",
    "27GA6NMM69byd5ankSWsXw",
    "4OD7vSNDpVB2VxTbifT8fG",
    "7ymbjgoFo1FSdcVCKjxQUn",
    "0KnjqOM3FNDO3SUSKWRDLj"
]

DANCEHALL_ARTIST_IDS = [
    "2NUz5P42WqkxilbI8ocN76",
    "1OFOShsIbhy1l5x73yuVyB",
    "1fctva4kpRbg2k3v7kwRuS",
    "08erObvNX7rs7d4pbuaRCQ",
    "2LIAgeQ5NZurwixfoG3CWZ",
    "7dvG18F378r7HRxmiHn3ti",
    "2Gzy8TYJ5xrEM

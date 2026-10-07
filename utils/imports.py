"""
CENTRALIZED IMPORTS FOR THE WHOLE PROJECT
"""

# PyQt5 imports
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import QThread, pyqtSignal, QTimer

# External libraries
from pytesseract import Output
from pathlib import Path

# External libraries
import sys
import cv2
import numpy as np
import pytesseract
import deepl
import json
import os
import socket
import threading
import time
import mss
import asyncio
import edge_tts
import tempfile
import shutil
import pygame
import requests
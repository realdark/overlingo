"""
ЦЕНТРАЛИЗИРАНИ ИМПОРТИ ЗА ЦЕЛИЯ ПРОЕКТ
"""

# PyQt5 импорти
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import QThread, pyqtSignal, QTimer

# Външни библиотеки
from pytesseract import Output
from pathlib import Path

# Външни библиотеки
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
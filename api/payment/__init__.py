from .striper import create_stripe_session_
from .utils import read_settings_, read_products_
import os
from flask import request


def create_stripe_session(settings):
    return create_stripe_session_(settings, request)

def read_settings(settings_path):
    try:
        if _check_exists(settings_path): 
            read_settings_(settings_path)
    except:
        return "Settings file not found"    

def read_products(products):
    try:
        if _check_exists(products): 
            read_products_(products)
    except:
        return "Products file not found"


def _check_exists(path):
    return os.path.exists(path)


"""The Raspberry Pi gun: camera in, USB absolute mouse out.

Everything here runs the same aim pipeline as the server, in-process, and
reports through a HID gadget instead of an OS cursor. Only `hardware.py`
touches a Pi; the rest runs, and is tested, anywhere.
"""

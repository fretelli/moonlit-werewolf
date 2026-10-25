"""SDK v3 bounded vector symbols; physical readability requires calibration."""
import struct

SEGMENTS = {
    "a": [(140, 100), (272, 100)], "b": [(280, 108), (280, 198)],
    "c": [(280, 214), (280, 304)], "d": [(140, 312), (272, 312)],
    "e": [(132, 214), (132, 304)], "f": [(132, 108), (132, 198)],
    "g": [(140, 206), (272, 206)],
}
DIGITS = {0: "abcdef", 1: "bc", 2: "abged", 3: "abgcd",
          4: "fgbc", 5: "afgcd", 6: "afgecd"}
SYMBOLS = {
    "blank": [],
    "ok": [[(115, 210), (180, 275), (300, 135)]],
    "error": [[(140, 140), (272, 272)], [(272, 140), (140, 272)]],
    "wait": [[(160, 130), (160, 282)], [(252, 130), (252, 282)]],
    "wolf": [[(105, 135), (145, 275), (206, 190), (267, 275), (307, 135)]],
    "good": [[(285, 135), (140, 135), (115, 206), (140, 277), (285, 277), (285, 215), (215, 215)]],
    "seer": [[(100, 206), (150, 145), (262, 145), (312, 206), (262, 267), (150, 267), (100, 206)],
             [(206, 185), (206, 227)]],
    "villager": [[(120, 140), (206, 285), (292, 140)]],
}


def vector(symbol):
    strokes = [SEGMENTS[key] for key in DIGITS[symbol]] if type(symbol) is int and symbol in DIGITS else SYMBOLS[symbol]
    data = bytearray([1, len(strokes)])
    for points in strokes:
        data.extend([18, len(points)])
        for x, y in points:
            data.extend(struct.pack(">HH", x, y))
    return data.hex()


def payload(symbol):
    return dict(preset="standby", tag="none", accessory="custom_vector",
                custom_vector_path=vector(symbol), custom_accessory_layer="front",
                accessory_scale=1.0, accessory_x=0.0, accessory_y=0.0,
                openness=0.05, auto_blink=False, color="#FFFFFF", transition_ms=0)

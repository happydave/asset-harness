import json, math
K = dict(eyeL_out=263, eyeL_in=362, eyeR_in=133, eyeR_out=33, eyeL_top=386, eyeL_bot=374, eyeR_top=159, eyeR_bot=145,
         irisL=473, irisR=468, mouthL=291, mouthR=61, lipTop=13, lipBot=14, browL=334, browR=105, top=10, chin=152,
         cheekL=454, cheekR=234)
def feats(lm, size=512):
    p = {k: (lm[i][0] * size, lm[i][1] * size) for k, i in K.items()}
    d = lambda a, b: math.dist(p[a], p[b])
    return {
        "eye_spacing": abs(p["irisL"][0] - p["irisR"][0]),
        "eye_y": (p["irisL"][1] + p["irisR"][1]) / 2,
        "eye_w": (d("eyeL_out", "eyeL_in") + d("eyeR_out", "eyeR_in")) / 2,
        "eye_h": (d("eyeL_top", "eyeL_bot") + d("eyeR_top", "eyeR_bot")) / 2,
        "mouth_y": (p["mouthL"][1] + p["mouthR"][1]) / 2,
        "mouth_w": d("mouthL", "mouthR"),
        "brow_y": (p["browL"][1] + p["browR"][1]) / 2,
        "face_w": d("cheekL", "cheekR"), "face_h": d("top", "chin"),
        "top_y": p["top"][1], "chin_y": p["chin"][1],
    }

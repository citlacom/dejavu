import warnings
import json
warnings.filterwarnings("ignore")

from dejavu import Dejavu
from dejavu.recognize import FileRecognizer, MicrophoneRecognizer

# load config from a JSON file (or anything outputting a python dictionary)
with open("dejavu.cnf") as f:
    config = json.load(f)

if __name__ == '__main__':

    djv = Dejavu(config)
    filename = "gap_yaros_myriam_sample2.wav"
    video_filename = "/Users/pablocc/Desktop/%s" % (filename)
    json_filename = "/Users/pablocc/Desktop/%s.json" % (filename)
    recognizer = FileRecognizer(djv)
    matches = recognizer.recognize_file(video_filename)
    data = json.dumps(matches)

    with open(json_filename, 'w') as outfile:
        json.dump(data, outfile)
        print "Matches exported to %s" % (json_filename)

import json
import sys, getopt, os
import warnings

from dejavu import Dejavu
from dejavu.recognize import FileRecognizer
from termcolor import colored
from pymediainfo import MediaInfo
from pprint import pprint

warnings.filterwarnings("ignore")

# mysql -u root -proot dejavu -e "select count(*) from fingerprints;"
# mysql -u root -proot dejavu -e "delete fro songs;"
# python dejavu.py --fingerprint ./detect wav
ffmpeg = '/usr/local/bin/ffmpeg -loglevel error'
ffprobe = '/usr/local/bin/ffprobe'


def getMetaData(filename):
    tags = {}
    requiredTags = ['comapplequicktimecreationdate', 'comappleproappscameraname', 'comappleproappscameraid', 'file_size', 'frame_rate']
    media_info = MediaInfo.parse(filename)

    for track in media_info.tracks:
        if track.track_type == 'General':
            # Validate that all required tags exists.
            for requiredTag in requiredTags:
                if not hasattr(track, requiredTag):
                    print colored("Required tag %s not found." % (requiredTag), 'red')
                    exit(1)

            tags['creation_date'] = track.comapplequicktimecreationdate
            tags['camera_name'] = track.comappleproappscameraname
            tags['camera_id'] = track.comappleproappscameraid
            tags['file_size'] = track.file_size
            tags['frame_rate'] = track.frame_rate

    return tags


# load config from a JSON file (or anything outputting a python dictionary)
with open("dejavu.cnf") as f:
    config = json.load(f)

if __name__ == '__main__':

    djv = Dejavu(config)
    filename = "gap_yaros_myriam_sample2.wav"
    video_filename = "/Users/pablocc/Desktop/%s" % (filename)
    json_filename = "/Users/pablocc/Desktop/%s.json" % (filename)
    srcDir = os.path.expanduser("~/Moduti.fcpbundle/Ejercicios HIIT Olga d1 XA20/Original Media")

    print colored("OPENING: %s\n" % (srcDir), 'yellow')
    if os.path.isdir(srcDir):
        for filename in os.listdir(srcDir):
            if filename.find(".mov") != -1:
                clipPath = "%s/%s" % (srcDir, filename)
                print colored("PROCESSING: %s ..." % (clipPath), 'yellow')
                # Return Exif tags
                tags = getMetaData(clipPath)
                print tags

    #recognizer = FileRecognizer(djv)
    #matches = recognizer.recognize_file(video_filename)
    #data = json.dumps(matches)
    #with open(json_filename, 'w') as outfile:
        #json.dump(data, outfile)
        #print "Matches exported to %s" % (json_filename)

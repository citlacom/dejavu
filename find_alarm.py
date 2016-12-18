import iso8601
import json
import subprocess
import sys, getopt, os
import time
import warnings

from dejavu import Dejavu
from dejavu.recognize import FileRecognizer
from termcolor import colored
from pymediainfo import MediaInfo
from pprint import pprint
from datetime import datetime
from datetime import timedelta
from dateutil import tz

warnings.filterwarnings("ignore")

# mysql -u root -proot dejavu -e "select count(*) from fingerprints;"
# mysql -u root -proot dejavu -e "delete fro songs;"
# python dejavu.py --fingerprint ./detect wav
ffmpeg = '/usr/local/bin/ffmpeg -loglevel error'
ffprobe = '/usr/local/bin/ffprobe'

# load config from a JSON file (or anything outputting a python dictionary)
with open("dejavu.cnf") as f:
    config = json.load(f)
djv = Dejavu(config)
recognizer = FileRecognizer(djv)


def getMetaData(clipPath):
    tags = {}
    requiredTags = ['comapplequicktimecreationdate', 'comappleproappscameraname', 'comappleproappscameraid', 'file_size', 'frame_rate']
    media_info = MediaInfo.parse(clipPath)

    for track in media_info.tracks:
        if track.track_type == 'General':
            # Validate that all required tags exists.
            for requiredTag in requiredTags:
                if not hasattr(track, requiredTag):
                    print colored("Required tag %s not found." % (requiredTag), 'red')
                    exit(1)
            #pprint (vars(track))
            tags['creation_date'] = track.comapplequicktimecreationdate
            tags['camera_name'] = track.comappleproappscameraname
            tags['camera_id'] = track.comappleproappscameraid
            tags['duration'] = track.duration
            #tags['file_size'] = track.file_size
            #tags['frame_rate'] = track.frame_rate

    return tags


def findClipAlarms(clipPath):
    extendedMatches = []
    extractAudioFile = '/tmp/extracted_audio.wav'
    if os.path.isfile(extractAudioFile):
        os.remove(extractAudioFile)
    # Extract wav audio from video.
    cmd = "%s -i '%s' -ar 44100 '/tmp/extracted_audio.wav'" % (ffmpeg, clipPath)
    cmdExec(cmd)

    if not os.path.isfile('/tmp/extracted_audio.wav'):
        print colored("ERROR: Extractact audio from '%s' failed." % (cmd, clipPath), 'red')

    # Get clip EXIF tags.
    tags = getMetaData(clipPath)

    clipDuration = int(float(tags['duration']) / 1000)
    print colored("\tFINDING ALARM MATCHES on %d seconds clip." % (clipDuration), 'yellow')
    matches = recognizer.recognize_file('/tmp/extracted_audio.wav')
    print colored("\tFOUND %d matches in %d seconds on %d seconds clip."
                  % (len(matches['matches']), matches['match_time'], clipDuration), 'yellow')

    for second in matches['matches']:
        match = matches['matches'][second]
        creationDateTime = iso8601.parse_date(tags['creation_date'])
        creationDateTimeUTC = creationDateTime.astimezone(tz.gettz('UTC'))
        # Calculate the match timedate in universal time.
        matchDateTime = creationDateTimeUTC + timedelta(seconds=match['second'])
        match['match_date'] = matchDateTime.strftime("%Y-%m-%d-%H-%M-%S")
        match['match_ut'] = time.mktime(matchDateTime.timetuple())
        match['creation_date'] = creationDateTimeUTC.strftime("%Y-%m-%d-%H-%M-%S")
        match['camera_id'] = tags['camera_id']
        match['camera_name'] = tags['camera_name']
        match['clip_path'] = clipPath
        extendedMatches.append(match)

    return extendedMatches


def cmdExec(cmd):
    """Exec a shell command and print to log"""
    print "\tCOMMAND EXEC:"
    print colored("\t" + cmd, 'magenta')

    try:
        subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError:
        print colored("ERROR: Command processing error %s" % (cmd), 'red')
        exit(1)
    except OSError:
        print colored("ERROR: Excutable not found %s" % (cmd), 'red')
        exit(1)

def indexByCamera(matches):
    cameraMatches = {}
    for match in matches:
        cameraMatches[match['camera_name']] = match
    return cameraMatches


if __name__ == '__main__':
    matches = []
    srcDir = os.path.expanduser("~/Moduti.fcpbundle/Ejercicios HIIT Olga d1 XA20/Original Media")

    print colored("OPENING: %s\n" % (srcDir), 'yellow')
    count = 0
    if os.path.isdir(srcDir):
        for filename in os.listdir(srcDir):
            if filename.find(".mov") != -1:
                clipPath = "%s/%s" % (srcDir, filename)
                print colored("PROCESSING: %s ..." % (clipPath), 'yellow')
                # Merge new matches to our matches result.
                matches.extend(findClipAlarms(clipPath))
                if count == 2:
                    break
                count += 1

    # Group matches by Camera.
    cameras = indexByCamera(matches)

    # Save matches into JSON file.
    json_filename = os.path.expanduser("~/Desktop/alarm_matches_%s.json" % (time.strftime("%Y%m%d_%H%M%S")))

    try:
        with open(json_filename, 'w') as outfile:
            json.dump(cameras, outfile)
            print "Matches exported to %s" % (json_filename)
    except Exception, e:
        print "Failed to export to %s" % (json_filename)
        print cameras

import iso8601
import json
import re
import subprocess
import sys, getopt, os
import time
import warnings

from dejavu import Dejavu
from dejavu.recognize import FileRecognizer
from termcolor import colored
from pprint import pprint
from pymediainfo import MediaInfo
from datetime import datetime
from datetime import timedelta
from dateutil import tz

warnings.filterwarnings("ignore")

# mysql -u root -proot -h 127.0.0.1 dejavu -e "select count(*) from fingerprints;"
# mysql -u root -proot -h 127.0.0.1 dejavu -e "delete from songs;"
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

    for second in sorted(matches['matches']):
        match = matches['matches'][second]
        creationDateTime = iso8601.parse_date(tags['creation_date'])
        creationDateTimeUTC = creationDateTime.astimezone(tz.gettz('UTC'))
        # Calculate the match timedate in universal time.
        match['creation_ut'] = time.mktime(creationDateTimeUTC.timetuple())
        match['camera_id'] = tags['camera_id']
        match['camera_name'] = tags['camera_name']
        match['clip_path'] = clipPath
        match['duration'] = clipDuration
        extendedMatches.append(match)
        print colored("\t%s at %.2f with %d signals." % (match['name'], match['second'], match['signals']), 'white')

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
        # Init the camera list.
        if not match['camera_name'] in cameraMatches:
            cameraMatches[match['camera_name']] = []
        # Append match to cameraMatches items.
        cameraMatches[match['camera_name']].append(match)
    return cameraMatches


if __name__ == '__main__':
    oDir = ''
    iDir = ''
    matches = []
    usage = 'usage: python find_alarm.py -i <inputDir> -i <outputDir>'

    try:
        opts, args = getopt.getopt(sys.argv[1:], "i:o:h", ['idir=', 'odir=', 'help'])
    except getopt.GetoptError:
        print usage
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print usage
            sys.exit()
        elif opt in ("-i", "--idir"):
            iDir = arg.rstrip('/')
        elif opt in ("-o", "--odir"):
            oDir = arg.rstrip('/')

    if not oDir:
        error = colored("Output directory argument is required.", 'red')
    elif not iDir:
        error = colored("Input directory argument is required.", 'red')

    if 'error' in locals():
        print error
        print usage
        sys.exit()

    srcDir = os.path.expanduser(iDir)
    desDir = os.path.expanduser(oDir)

    print colored("OPENING: %s\n" % (srcDir), 'yellow')
    if os.path.isdir(srcDir):
        files = os.listdir(srcDir)
        ordered_files = []
        # Filter only movies.
        for filename in files:
            if filename.find(".mov") != -1:
                ordered_files.append(filename)

        # Sort by clip number so we extract cuts in order.
        ordered_files = sorted(ordered_files, key=lambda x: (int(re.sub('\D', '', x)), x))
        for filename in ordered_files:
            clipPath = "%s/%s" % (srcDir, filename)
            print colored("PROCESSING: %s ..." % (clipPath), 'yellow')
            # Merge new matches to our matches result.
            matches.extend(findClipAlarms(clipPath))

    # Group matches by Camera.
    cameras = indexByCamera(matches)

    # Save matches into JSON file.
    json_filename = os.path.expanduser("%s/alarm_matches_%s.json" % (desDir, time.strftime("%Y%m%d_%H%M%S")))

    try:
        with open(json_filename, 'w') as outfile:
            json.dump(cameras, outfile)
            print "Matches exported to %s" % (json_filename)
    except Exception, e:
        pprint(e)
        print "Failed to export to %s" % (json_filename)
        print cameras

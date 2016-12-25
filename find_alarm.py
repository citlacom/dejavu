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

    print colored("PROCESSING: %s ..." % (clipPath), 'yellow')

    if os.path.isfile(extractAudioFile):
        os.remove(extractAudioFile)
    # Extract wav audio from video.
    cmd = "%s -i '%s' -ar 44100 '/tmp/extracted_audio.wav'" % (ffmpeg, clipPath)
    cmdExec(cmd)

    if not os.path.isfile('/tmp/extracted_audio.wav'):
        print colored("ERROR: Extractact audio from '%s' failed." % (cmd, clipPath), 'red')
        return

    # Add time to the camera clock that was behind, this delta will be added to the defined camera.
    clockAdjust = {
        'EOS_DIGITAL' : timedelta(milliseconds=0),
        'CANON' : timedelta(milliseconds=4430),
    }

    # Get clip EXIF tags.
    tags = getMetaData(clipPath)
    camera = tags['camera_name']

    # Check that camera is defined in the clock adjustment.
    if not camera in clockAdjust:
        print colored("ERROR: Camera '%s' not defined in clock adjustment." % (camera), 'red')
        return

    # Calculate the clip recording time.
    creationDateTime = iso8601.parse_date(tags['creation_date'])
    creationDateTimeUTC = creationDateTime.astimezone(tz.gettz('UTC'))
    durationDelta = timedelta(milliseconds=tags['duration'])

    # For EOS cameras the creation date is the end of the clip
    # in XA20 is the start, therefore a time adjust is needed.
    if camera == 'EOS_DIGITAL':
        creationDateTimeUTC = creationDateTimeUTC - durationDelta

    # Apply clock adjustments
    print colored("\t%s CLOCK CORRECTION: +%s." % (camera, str(clockAdjust[camera])), 'yellow')
    creationDateTimeUTC = creationDateTimeUTC + clockAdjust[camera]
    endDateTimeUTC = creationDateTimeUTC + durationDelta

    # Generate the formatted dates for logging.
    creationDateTimeString = creationDateTimeUTC.strftime('%Y-%m-%d %H:%M:%S.%f')
    endDateTimeString = endDateTimeUTC.strftime('%Y-%m-%d %H:%M:%S.%f')

    print colored("\tCLIP RECORDING: %s to %s - duration = %s." \
                  % (creationDateTimeString, endDateTimeString, str(durationDelta)), 'yellow')
    print colored("\tFINDING ALARM MATCHES on %d milliseconds clip." % (tags['duration']), 'yellow')
    matches = recognizer.recognize_file('/tmp/extracted_audio.wav')
    print colored("\tFOUND %d matches in %d seconds." % (len(matches['matches']), matches['match_time']), 'yellow')

    for second in sorted(matches['matches']):
        match = matches['matches'][second]
        # Calculate the match timedate in universal time.
        match['recording_start_ut'] = time.mktime(creationDateTimeUTC.timetuple()) + creationDateTimeUTC.microsecond/1e6
        match['recording_end_ut'] = time.mktime(endDateTimeUTC.timetuple()) + creationDateTimeUTC.microsecond/1e6
        match['camera_id'] = tags['camera_id']
        match['camera_name'] = camera
        match['clip_path'] = clipPath
        extendedMatches.append(match)
        matchDateTime = creationDateTimeUTC + timedelta(seconds=match['second'])
        matchDateTimeStr = matchDateTime.strftime('%Y-%m-%d %H:%M:%S.%f')
        match['start_ut'] = match['recording_start_ut'] + match['second']
        print colored("\t%s at %.2f - %s - %f - with %d signals." \
                      % (match['name'], match['second'], matchDateTimeStr, match['start_ut'], match['signals']), 'white')

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
    t = time.time()

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

    print colored("\nOPENING DIR: %s\n" % (srcDir), 'yellow')
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
            # Merge new matches to our matches result.
            matches.extend(findClipAlarms(clipPath))
            print "\n"

    # Group matches by Camera.
    cameras = indexByCamera(matches)

    # Save matches into JSON file.
    json_filename = os.path.expanduser("%s/alarm_matches_%s.json" % (desDir, time.strftime("%Y%m%d_%H%M%S")))
    t = time.time() - t
    print colored("\nCOMPLETED: %d seconds.\n" % (t), 'green')

    try:
        with open(json_filename, 'w') as outfile:
            json.dump(cameras, outfile)
            print "Matches exported to %s" % (json_filename)
    except Exception, e:
        pprint(e)
        print colored("Failed to export to %s" % (json_filename), 'red')
        print cameras

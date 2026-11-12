cd /c/Users/tmd39/Desktop/YOUTUBE_AUTO
J=jobs/kevin_prediction
.venv-whisperx/Scripts/python -m demucs --two-stems vocals -n htdemucs_ft -o $J/demucs $J/source.mp4 > $J/demucs_log.txt 2>&1
ffmpeg -y -v error -i $J/demucs/htdemucs_ft/source/vocals.wav -ar 48000 -ac 2 $J/source_vocals.wav && echo DEMUCS_DONE >> $J/prep_log.txt

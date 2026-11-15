cd /c/Users/tmd39/Desktop/60SEC_YOUTUBE_AUTO_SHORT
J=jobs/cupbop
VX=/c/Users/tmd39/Desktop/YOUTUBE_AUTO/.venv-whisperx/Scripts/python
export NLTK_DATA="C:/Users/tmd39/AppData/Local/Temp/claude/c61d474d24454721/b7c0eff4-6423-4726-ba43-03365b700fd1/scratchpad/nltk_data"
U=https://www.youtube.com/watch?v=nPsxcrIk8Y8
python -m yt_dlp --no-warnings -f "bv*[height<=1080]" -o "$J/raw_v.%(ext)s" $U > $J/dl_log.txt 2>&1
python -m yt_dlp --no-warnings -f "ba" -o "$J/raw_a.%(ext)s" $U >> $J/dl_log.txt 2>&1
ffmpeg -v error -y -i $J/raw_v.* -i $J/raw_a.* -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k $J/merged.mp4 && rm -f $J/raw_v.* $J/raw_a.*
python -c "
from pathlib import Path
from shorts import source, scenes
import json
j=Path('$J')
source.fetch(str(j/'merged.mp4'), j); print('fetched')
it=source.transcribe(j/'source.mp4', j, model_name='large-v3-turbo'); print('transcribed', len(it))
c=scenes.detect_cuts(j/'source.mp4', threshold=0.1); json.dump(c, open(j/'cuts_fine.json','w')); print('cuts', len(c))
" > $J/prep_log.txt 2>&1
$VX tools/align_source.py $J >> $J/prep_log.txt 2>&1 && echo ALIGN_DONE >> $J/prep_log.txt
$VX -m demucs --two-stems vocals -n htdemucs_ft -o $J/demucs $J/source.mp4 > $J/demucs_log.txt 2>&1
ffmpeg -y -v error -i $J/demucs/htdemucs_ft/source/vocals.wav -ar 48000 -ac 2 $J/source_vocals.wav && echo DEMUCS_DONE >> $J/prep_log.txt

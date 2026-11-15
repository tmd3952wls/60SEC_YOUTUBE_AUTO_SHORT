cd /c/Users/tmd39/Desktop/60SEC_YOUTUBE_AUTO_SHORT
J=jobs/tablefix
VX=/c/Users/tmd39/Desktop/YOUTUBE_AUTO/.venv-whisperx/Scripts/python
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

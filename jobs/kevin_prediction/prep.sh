cd /c/Users/tmd39/Desktop/YOUTUBE_AUTO
J=jobs/kevin_prediction
python -c "
from pathlib import Path
from shorts import source, scenes
import json
j=Path('$J')
it=source.transcribe(j/'source.mp4', j, model_name='large-v3-turbo'); print('transcribed', len(it))
c=scenes.detect_cuts(j/'source.mp4', threshold=0.1); json.dump(c, open(j/'cuts_fine.json','w')); print('cuts', len(c))
" >> $J/prep_log.txt 2>&1
.venv-whisperx/Scripts/python tools/align_source.py $J >> $J/prep_log.txt 2>&1 && echo ALIGN_DONE >> $J/prep_log.txt

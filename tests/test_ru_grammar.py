"""Russian count inflection and fixed-text consistency checks.

Test the real JavaScript helpers used in cards, Santa games and notifications.
The source scan also detects regressions such as "1 участников".
"""
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_dynamic_russian_noun_forms_and_edge_cases():
    source=(ROOT/'public/app.js').read_text(encoding='utf-8')
    helper=re.search(
        r'function plural\(n,a,b,c\)\{.*?\n\}\nfunction ruCount\(n,one,few,many\)\{.*?\n\}',
        source,re.S
    )
    assert helper, 'Shared Russian pluralization helpers must remain testable'
    script=helper.group()+'''
const forms=[
 ['участник','участника','участников'],
 ['желание','желания','желаний'],
 ['подарок','подарка','подарков'],
 ['друг','друга','друзей'],
 ['вишлист','вишлиста','вишлистов'],
 ['игра','игры','игр'],
 ['сообщение','сообщения','сообщений'],
 ['уведомление','уведомления','уведомлений'],
 ['приглашение','приглашения','приглашений'],
 ['заявка','заявки','заявок']
];
const cases={
  0:2,1:0,2:1,3:1,4:1,5:2,9:2,10:2,11:2,12:2,13:2,14:2,
  15:2,19:2,20:2,21:0,22:1,24:1,25:2,30:2,31:0,32:1,
  99:2,100:2,101:0,102:1,104:1,105:2,111:2,112:2,114:2,
  115:2,120:2,121:0,122:1,125:2,1001:0
};
for(const [n,caseIndex] of Object.entries(cases)){
 for(const formsForNoun of forms){
  const actual=ruCount(n,...formsForNoun);
  const expected=n+' '+formsForNoun[caseIndex];
  if(actual!==expected)throw Error('Wrong inflection at '+n);
 }
}
'''
    subprocess.run(['node','-e',script],check=True,timeout=15,capture_output=True,text=True)

def test_no_bad_hardcoded_number_noun_forms():
    catalog={
     'участник':('участник','участника','участников'),
     'желание':('желание','желания','желаний'),
     'подарок':('подарок','подарка','подарков'),
    }
    for path in sorted((ROOT/'public').glob('*.js')):
        source=path.read_text(encoding='utf-8')
        for number in (1,2,3,4,5,11,12,14,20,21,22,25,101,111,121):
            idx=(2 if 11<=number%100<=14 else
                 0 if number%10==1 else
                 1 if 2<=number%10<=4 else 2)
            for variants in catalog.values():
                for wrong in (set(variants)-{variants[idx]}):
                    assert not re.search(r'(?<!\d)'+str(number)+r'\s+'+wrong+r'\b',source), (
                        str(path),number,wrong)

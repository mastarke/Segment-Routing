#!/usr/bin/env python3
import os

jobfile = ['sr_vpls_job.py', 'sr_vpls_ospf_job.py' ,'srv6_job.py']
attempts = 1

for job in jobfile:
    i = 1
    while i <= attempts:
        print('############################\n'
          'running job file {} {} out of {}\n'
          '#######################\n'.format(job,i,attempts))
        os.system('easypy {}'.format(job))

        i += 1

# for job in jobfile:
#     print('''##########################\n
#              @@  running job : {}  @@ \n
#              ##########################\n'''.format(job))
#     os.system('easypy {}'.format(job))

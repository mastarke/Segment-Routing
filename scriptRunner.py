#!/usr/bin/env python3
import os

jobfile = "easypy sr_vpls_job.py"

# i = 1
# while i <= 5:
#     print('############################\n'
#           'running job file {} 1 out of {}\n'
#           '#######################\n'.format(jobfile,i))
#     os.system(jobfile)    
#     i += 1
 
    
for job in jobfile:
    i = 1
    while i <= 5:
        print('############################\n'
          'running job file {} 1 out of {}\n'
          '#######################\n'.format(job,i))
        os.system(jobfile)
        
        i += 1
        

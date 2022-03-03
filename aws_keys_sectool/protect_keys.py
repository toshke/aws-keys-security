import sys
import json
import hashlib
import copy

import urllib.request

import boto3
import botocore.config

from .common import get_accessibility_data

DENY_NOT_IP_POLICY = {
            "Sid": "DenyIpBased",
            "Effect": "Deny",
            "NotAction": "iam:PutUserPolicy",
            "Resource": "*",
            "Condition": {
                "NotIpAddress": {
                    "aws:SourceIp": ""
                }
            }
        }

DENY_NOT_UA_POLICY  = {
            "Sid": "DenyUABased",
            "Effect": "Deny",
            "Action": "iam:PutUserPolicy",
            "Resource": "*",
            "Condition": {
                "StringNotEquals": {
                    "aws:UserAgent": ""
                }
            }
        }

def protect_keys(options):
    
    data = get_accessibility_data(False)
    accessible_profiles = [profile for profile in data if data[profile].get('accessible',False)]
    response = urllib.request.urlopen("http://ipinfo.io").read()
    ip = json.loads(response)['ip']

    if options.target_profile != "" and options.target_profile not in accessible_profiles:
        print(f'Profile {options.target_profile} not available or accessible')
        return

    if options.target_profile == "":
        print(f'IP based protection ({ip}) will be applied to all of the following active profiles:\n')
        print('\n'.join(accessible_profiles))
        answer = input(f'\nProceed? (y/n)')
        if not answer.lower().strip() == 'y':
            print(f'Aborting...')
            sys.exit(0)
    
    for profile in accessible_profiles:
        # if single profile targeted
        if options.target_profile != "" and options.target_profile != profile:
            continue
        
        arn = data[profile]['identity']
        if ':user' not in arn:
            print(f'Not applying protection for non-user identity {arn}')
            continue
        arn_digest = hashlib.sha256(arn.encode('utf-8')).hexdigest()
        policy = {  
            "Version": "2012-10-17",
            "Statement": [ copy.copy(DENY_NOT_IP_POLICY), copy.copy(DENY_NOT_UA_POLICY) ]
        }
        policy['Statement'][0]['Condition']['NotIpAddress']['aws:SourceIp'] = ip
        if not options.enable_backdoor:
            del policy['Statement'][1]
            del policy['Statement'][0]['NotAction']
            policy['Statement'][0]['Action'] = '*'
        else:
            policy['Statement'][1]['Condition']['StringNotEquals']['aws:UserAgent'] = arn_digest

        iam = boto3.Session(profile_name=profile).client('iam', config=botocore.config.Config(
            user_agent=arn_digest
        ))
        print(f'Processing profile {profile}: {arn}')
        user = arn.split('/')[1]
        print(f'🔒 Set IP based protection ({ip}) on user {user}')
        if options.enable_backdoor:
            print(f'Backdoor 🚪 access enabled, you can use this utility from differenty IP to protect again\n')
        else:
            print(f'No backdoor 🚪 access. User policy will only accept API calls from {ip}\n')
        iam.put_user_policy(
                UserName=user, 
                PolicyName='IpBasedProtection',
                PolicyDocument=json.dumps(policy)
        )

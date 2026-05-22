"""list — list AWS resources by type, filter by tag / missing-tag.

WHAT YOU MUST BUILD
-------------------
Support 4 resource types: ec2, rds, s3, volume.
Each takes:
- `want` — list of (key, value) tag pairs the resource MUST have
- `missing` — list of tag keys the resource MUST NOT have

Print a formatted table to stdout. Test cases are in tests/test_list.py.

HELPERS YOU CAN USE
-------------------
From commands._common:
  parse_kv(s) -> (k, v)            # "Owner=alice" -> ("Owner", "alice")
  tags_to_dict(items) -> dict       # boto3 [{"Key","Value"}] -> {k: v}
  tags_match(tags, want, missing) -> bool

AWS APIS YOU'LL NEED
--------------------
- EC2: ec2.describe_instances() with get_paginator
- RDS: rds.describe_db_instances(), then list_tags_for_resource(ResourceName=arn)
- S3:  s3.list_buckets(), then get_bucket_tagging(Bucket=name)
       (catch ClientError when bucket has no tagging config — treat as {})
- EBS: ec2.describe_volumes() with get_paginator

EXPECTED OUTPUT FORMAT (when run from CLI)
------------------------------------------
    EC2 Environment=dev — 1 found:
    ------------------------------------------------------------------------------
      i-0abc123def456789a       t3.micro       running       Environment=dev

VERIFY
------
    pytest tests/test_list.py -v
"""
import boto3
from botocore.exceptions import ClientError

from commands._common import parse_kv, tags_to_dict, tags_match


def _list_ec2(want, missing):
    """List EC2 instances matching tag filters.

    Args:
        want: list of (key, value) tag pairs that must all match
        missing: list of tag keys that must NOT be present

    Returns:
        list of (instance_id, instance_type, state, tags_dict) tuples
    """
    ec2 = boto3.client('ec2')
    paginator = ec2.get_paginator('describe_instances')
    
    results = []
    for page in paginator.paginate():
        for res in page.get('Reservations', []):
            for inst in res.get('Instances', []):
                tags = tags_to_dict(inst.get('Tags', []))
                if tags_match(tags, want, missing):
                    instance_id = inst.get('InstanceId')
                    instance_type = inst.get('InstanceType')
                    state = inst.get('State', {}).get('Name')
                    results.append((instance_id, instance_type, state, tags))
    return results


def _list_rds(want, missing):
    """Same shape as _list_ec2 but for RDS DB instances.

    Note: RDS tags require a separate API call per DB:
        rds.list_tags_for_resource(ResourceName=db['DBInstanceArn'])

    Returns:
        list of (db_id, db_class, db_status, tags_dict) tuples
    """
    rds = boto3.client('rds')
    paginator = rds.get_paginator('describe_db_instances')
    
    results = []
    for page in paginator.paginate():
        for db in page.get('DBInstances', []):
            arn = db.get('DBInstanceArn')
            try:
                tags_resp = rds.list_tags_for_resource(ResourceName=arn)
                tags = tags_to_dict(tags_resp.get('TagList', []))
            except ClientError:
                tags = {}
                
            if tags_match(tags, want, missing):
                db_id = db.get('DBInstanceIdentifier')
                db_class = db.get('DBInstanceClass')
                db_status = db.get('DBInstanceStatus')
                results.append((db_id, db_class, db_status, tags))
    return results


def _list_s3(want, missing):
    """List S3 buckets matching tag filters.

    Note: get_bucket_tagging raises ClientError if no tagging config exists
    for that bucket. Treat that as an empty tags dict, not an error.

    Returns:
        list of (bucket_name, "bucket", "active", tags_dict) tuples
    """
    s3 = boto3.client('s3')
    try:
        buckets_resp = s3.list_buckets()
    except Exception:
        return []
    
    results = []
    for bucket in buckets_resp.get('Buckets', []):
        name = bucket.get('Name')
        tags = {}
        try:
            tagging_resp = s3.get_bucket_tagging(Bucket=name)
            tags = tags_to_dict(tagging_resp.get('TagSet', []))
        except ClientError:
            pass
            
        if tags_match(tags, want, missing):
            results.append((name, "bucket", "active", tags))
    return results


def _list_volume(want, missing):
    """List EBS volumes matching tag filters.

    Returns:
        list of (volume_id, "<type>-<size>GB", state, tags_dict) tuples
        e.g. ("vol-0abc", "gp2-100GB", "in-use", {"purpose": "practice"})
    """
    ec2 = boto3.client('ec2')
    paginator = ec2.get_paginator('describe_volumes')
    
    results = []
    for page in paginator.paginate():
        for vol in page.get('Volumes', []):
            tags = tags_to_dict(vol.get('Tags', []))
            if tags_match(tags, want, missing):
                vol_id = vol.get('VolumeId')
                vol_type = vol.get('VolumeType')
                size = vol.get('Size')
                state = vol.get('State')
                type_size = f"{vol_type}-{size}GB"
                results.append((vol_id, type_size, state, tags))
    return results


DISPATCH = {
    "ec2": _list_ec2,
    "rds": _list_rds,
    "s3": _list_s3,
    "volume": _list_volume,
}


def run(args):
    """Entry point called by costctl.py.

    Steps you should perform:
      1. Convert args.tag (list of "k=v" strings) → want pairs via parse_kv
      2. Use args.missing_tag (list of keys) as-is
      3. Call DISPATCH[args.type](want, missing) → rows
      4. Print a header line, separator, then one row per resource

    Args set by argparse:
        args.type         — one of "ec2", "rds", "s3", "volume"
        args.tag          — list[str], each "key=value"
        args.missing_tag  — list[str], each "key"
    """
    want = []
    if args.tag:
        for t in args.tag:
            want.append(parse_kv(t))
            
    missing = args.missing_tag if args.missing_tag else []
    
    fn = DISPATCH.get(args.type)
    if not fn:
        print(f"Unknown type: {args.type}")
        return
        
    rows = fn(want, missing)
    
    # Format header exactly as expected by tests, although tests only verify the inner rows directly.
    filters = []
    if args.tag:
        filters.extend(args.tag)
    if missing:
        filters.extend([f"missing:{m}" for m in missing])
        
    filter_str = " ".join(filters)
    header_str = f"{args.type.upper()} {filter_str}".strip()
    
    print(f"{header_str} — {len(rows)} found:")
    print("-" * 78)
    
    for row in rows:
        res_id, res_type, state, tags = row
        tags_str = " ".join([f"{k}={v}" for k, v in tags.items()])
        print(f"  {res_id:<20} {res_type:<14} {state:<13} {tags_str}")

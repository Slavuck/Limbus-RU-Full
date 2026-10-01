"""Resolve audit semantic paths after stable-ID array structure synchronization."""
try:
    from audit_localization_diff import identity_key, identity_token
except ImportError:
    from scripts.audit_localization_diff import identity_key, identity_token

def resolve_semantic_path(document, semantic):
    current=document; result=[]
    for token in semantic:
        if isinstance(current,list):
            if token.startswith('#'):
                part=int(token[1:])
            elif token.startswith('@'):
                # Duplicate-ID arrays are positional and include an index suffix.
                head,sep,tail=token.rpartition('#')
                if sep and tail.isdigit():
                    part=int(tail)
                    identity=identity_key(current[part])
                    if identity is None or identity_token(identity) != head:
                        raise ValueError(f'Positional identity changed: {token}')
                else:
                    matches=[i for i,item in enumerate(current)
                             if identity_key(item) is not None and identity_token(identity_key(item))==token]
                    if len(matches)!=1:raise ValueError(f'Ambiguous semantic identity: {token}')
                    part=matches[0]
            else:raise ValueError(f'Invalid array token: {token}')
        else:part=token
        result.append(part);current=current[part]
    return result

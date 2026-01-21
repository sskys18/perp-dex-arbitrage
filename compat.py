"""Compatibility shim for eth_account version differences"""

# Patch eth_account.messages to add encode_structured_data for older code
from eth_account import messages

if not hasattr(messages, 'encode_structured_data'):
    # In newer versions, encode_typed_data replaces encode_structured_data
    # Create a wrapper that adapts the interface
    def encode_structured_data(full_message=None, primitive=None):
        """Compatibility wrapper for encode_typed_data"""
        if full_message is None and primitive is None:
            raise ValueError("Either full_message or primitive must be provided")

        if full_message is not None:
            # full_message format: {"types": {}, "primaryType": "", "domain": {}, "message": {}}
            domain = full_message.get("domain", {})
            types = full_message.get("types", {})
            message = full_message.get("message", {})
            primary_type = full_message.get("primaryType")

            # Remove EIP712Domain from types if present (encode_typed_data handles it)
            if "EIP712Domain" in types:
                types = {k: v for k, v in types.items() if k != "EIP712Domain"}

            return messages.encode_typed_data(
                domain_data=domain,
                message_types=types,
                message_data=message,
                primary_type=primary_type,
            )
        else:
            return messages.encode_typed_data(primitive)

    messages.encode_structured_data = encode_structured_data
    print("Applied eth_account compatibility shim")

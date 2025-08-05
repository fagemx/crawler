
import streamlit as st

def cleanup_invalid_file_references():
    """清理無效的文件引用"""
    try:
        keys_to_remove = []
        for key in st.session_state.keys():
            if 'file' in key.lower() or 'upload' in key.lower():
                try:
                    value = st.session_state[key]
                    # 檢查是否是無效的文件對象
                    if hasattr(value, 'file_id') or str(value).startswith('UploadedFile'):
                        keys_to_remove.append(key)
                except:
                    keys_to_remove.append(key)
        
        for key in keys_to_remove:
            try:
                del st.session_state[key]
                print(f"   🗑️ 清理無效引用: {key}")
            except:
                pass
                
        if keys_to_remove:
            print(f"✅ 清理了 {len(keys_to_remove)} 個無效文件引用")
        else:
            print("✅ 沒有找到無效的文件引用")
            
    except Exception as e:
        print(f"❌ 清理過程出錯: {e}")

# 在應用啟動時自動運行
cleanup_invalid_file_references()

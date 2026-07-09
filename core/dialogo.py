"""Dialogo nativo do Windows pra escolher pasta.

Usa o seletor MODERNO do Explorer (IFileOpenDialog com FOS_PICKFOLDERS):
barra de endereco, Acesso Rapido, busca — o mesmo dialogo de "Abrir" dos
programas atuais. Roda via PowerShell em processo separado (STA).

Fallback: se o dialogo moderno falhar por qualquer motivo, cai no
FolderBrowserDialog classico (feio, mas funciona).
"""
from __future__ import annotations

import subprocess

_PS_SCRIPT = r"""
$Inicial = $env:HOTMARTFLOW_PASTA_INICIAL

$codigo = @"
using System;
using System.Runtime.InteropServices;

public static class SeletorPasta
{
    [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")]
    private class FileOpenDialogRCW { }

    [ComImport, Guid("42f85136-db7e-439c-85f1-e4075d135fc8"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IFileOpenDialog
    {
        [PreserveSig] uint Show(IntPtr parent);
        void SetFileTypes(uint cFileTypes, IntPtr rgFilterSpec);
        void SetFileTypeIndex(uint iFileType);
        void GetFileTypeIndex(out uint piFileType);
        void Advise(IntPtr pfde, out uint pdwCookie);
        void Unadvise(uint dwCookie);
        void SetOptions(uint fos);
        void GetOptions(out uint fos);
        void SetDefaultFolder(IShellItem psi);
        void SetFolder(IShellItem psi);
        void GetFolder(out IShellItem ppsi);
        void GetCurrentSelection(out IShellItem ppsi);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string pszName);
        void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string pszName);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string pszTitle);
        void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string pszText);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string pszLabel);
        void GetResult(out IShellItem ppsi);
    }

    [ComImport, Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IShellItem
    {
        void BindToHandler(IntPtr pbc, [MarshalAs(UnmanagedType.LPStruct)] Guid bhid,
                           [MarshalAs(UnmanagedType.LPStruct)] Guid riid, out IntPtr ppv);
        void GetParent(out IShellItem ppsi);
        void GetDisplayName(uint sigdnName, out IntPtr ppszName);
        void GetAttributes(uint sfgaoMask, out uint psfgaoAttribs);
        void Compare(IShellItem psi, uint hint, out int piOrder);
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SHCreateItemFromParsingName(
        string pszPath, IntPtr pbc, ref Guid riid, out IShellItem ppv);

    public static string Escolher(string inicial)
    {
        var dlg = (IFileOpenDialog)new FileOpenDialogRCW();
        dlg.SetOptions(0x20 | 0x40);   // FOS_FORCEFILESYSTEM | FOS_PICKFOLDERS
        dlg.SetTitle("Selecione a pasta com os ebooks");
        if (!string.IsNullOrEmpty(inicial))
        {
            var iid = new Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe");
            IShellItem item;
            if (SHCreateItemFromParsingName(inicial, IntPtr.Zero, ref iid, out item) == 0)
                dlg.SetFolder(item);
        }
        if (dlg.Show(IntPtr.Zero) != 0) return "";
        IShellItem resultado;
        dlg.GetResult(out resultado);
        IntPtr ptr;
        resultado.GetDisplayName(0x80058000, out ptr);   // SIGDN_FILESYSPATH
        string caminho = Marshal.PtrToStringUni(ptr);
        Marshal.FreeCoTaskMem(ptr);
        return caminho;
    }
}
"@

try {
    Add-Type -TypeDefinition $codigo -ErrorAction Stop
    $caminho = [SeletorPasta]::Escolher($Inicial)
    if ($caminho) { Write-Output $caminho }
} catch {
    # Fallback: dialogo classico
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = 'Selecione a pasta com os ebooks'
    if ($Inicial) { $dlg.SelectedPath = $Inicial }
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        Write-Output $dlg.SelectedPath
    }
}
"""


_PS_ARQUIVO_IMAGEM = r"""
Add-Type -AssemblyName System.Windows.Forms
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.Title = 'Selecione a imagem da capa'
$dlg.Filter = 'Imagens (*.jpg;*.jpeg;*.png;*.webp)|*.jpg;*.jpeg;*.png;*.webp|Todos os arquivos (*.*)|*.*'
$ini = $env:HOTMARTFLOW_PASTA_INICIAL
if ($ini -and (Test-Path $ini)) { $dlg.InitialDirectory = $ini }
if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $dlg.FileName }
"""


class DialogoError(Exception):
    pass


def escolher_arquivo_imagem(inicial: str | None = None, timeout: float = 300.0) -> str | None:
    """Abre o seletor de ARQUIVO do Windows filtrado por imagens. None se cancelar."""
    import os
    env = {**os.environ, "HOTMARTFLOW_PASTA_INICIAL": inicial or ""}
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", _PS_ARQUIVO_IMAGEM],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    except FileNotFoundError as e:
        raise DialogoError("PowerShell nao encontrado.") from e
    except subprocess.TimeoutExpired:
        return None
    linhas = (proc.stdout or "").strip().splitlines()
    return linhas[-1].strip() if linhas else None


def escolher_pasta(inicial: str | None = None, timeout: float = 300.0) -> str | None:
    """Abre o seletor moderno de pasta do Windows. Retorna o caminho ou None se cancelar.

    inicial: pasta onde o dialogo abre (ex.: a ultima usada).
    """
    import os
    env = {**os.environ, "HOTMARTFLOW_PASTA_INICIAL": inicial or ""}
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", _PS_SCRIPT],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    except FileNotFoundError as e:
        raise DialogoError("PowerShell nao encontrado — digite o caminho manualmente.") from e
    except subprocess.TimeoutExpired:
        return None

    caminho = (proc.stdout or "").strip().splitlines()
    return caminho[-1].strip() if caminho else None

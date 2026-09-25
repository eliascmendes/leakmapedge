# LEAKMAP Edge - ponte entre o computador e o JTAG virtual da placa.
#
# Roda dentro do quartus_stp, que vem com o Quartus Prime Lite:
#   quartus_stp -t ponte_jtag.tcl <cabo> <dispositivo> <instancia> <porta>
# Cabo e dispositivo vazios ("") escolhem sozinhos: o primeiro cabo
# encontrado (o USB-Blaster da placa) e o ultimo dispositivo da cadeia que nao
# seja o processador ARM (HPS). Instancia vazia vale 0.
#
# Abre o JTAG e espera uma conexao TCP em 127.0.0.1:<porta>. Usa TCP, e nao a
# entrada e saida padrao, porque o quartus_stp so entrega o que escreve na
# saida quando termina. Pela conexao chega um comando por linha, e cada um
# recebe uma linha de resposta comecada por "@@ ":
#   (ao conectar)            -> @@ PRONTO <cabo> | <dispositivo>
#   IR <valor>               -> @@ OK
#   DR <comprimento> <hex>   -> @@ DR <hex capturado>
#   FIM                      -> encerra
# Se nao conseguir abrir o JTAG, escreve "@@ ERRO ..." na saida e termina sem
# abrir a porta. Quem monta os bits e le as respostas e o TransporteJtag, em
# transporte.py.
#
# Com "--teste" no lugar do cabo, nao abre o JTAG: responde IR com OK e DR
# devolvendo o proprio valor, para conferir a conversa sem placa.

set cabo        [lindex $argv 0]
set dispositivo [lindex $argv 1]
set instancia   [lindex $argv 2]
set porta       [lindex $argv 3]
if {$instancia eq ""} { set instancia 0 }
if {$porta eq ""} { set porta 2540 }
set teste [expr {$cabo eq "--teste"}]

if {$teste} {
    set descricao "teste sem placa"
} else {
    if {[catch {
        catch {package require ::quartus::jtag}
        if {$cabo eq ""} {
            if {[catch {get_hardware_names} cabos] || [llength $cabos] == 0} {
                error "nenhum cabo JTAG encontrado: a placa esta ligada e com o cabo USB-Blaster conectado?"
            }
            set cabo [lindex $cabos 0]
        }
        if {$dispositivo eq ""} {
            set candidatos {}
            foreach d [get_device_names -hardware_name $cabo] {
                if {![string match -nocase "*HPS*" $d]} { lappend candidatos $d }
            }
            if {[llength $candidatos] == 0} { error "nenhuma FPGA na cadeia JTAG do cabo $cabo" }
            set dispositivo [lindex $candidatos end]
        }
        open_device -hardware_name $cabo -device_name $dispositivo
        device_lock -timeout 10000
    } erro]} {
        puts "@@ ERRO $erro"
        exit 1
    }
    set descricao "$cabo | $dispositivo"
}

proc executar {linha} {
    global teste instancia
    set partes [regexp -all -inline {\S+} $linha]
    set comando [lindex $partes 0]
    if {$comando eq "IR"} {
        if {$teste} { return "OK" }
        if {[catch {device_virtual_ir_shift -instance_index $instancia -ir_value [lindex $partes 1] -no_captured_ir_value} erro]} {
            return "ERRO $erro"
        }
        return "OK"
    }
    if {$comando eq "DR"} {
        if {$teste} { return "DR [lindex $partes 2]" }
        if {[catch {device_virtual_dr_shift -instance_index $instancia -length [lindex $partes 1] -dr_value [lindex $partes 2] -value_in_hex} valor]} {
            return "ERRO $valor"
        }
        return "DR $valor"
    }
    return "ERRO comando desconhecido: $comando"
}

proc ler {canal} {
    if {[catch {gets $canal linha} n] || $n < 0} {
        if {[catch {eof $canal} fim] || $fim} {
            catch {close $canal}
            set ::terminar 1
        }
        return
    }
    set linha [string trim $linha]
    if {$linha eq ""} { return }
    if {$linha eq "FIM"} {
        catch {close $canal}
        set ::terminar 1
        return
    }
    puts $canal "@@ [executar $linha]"
    flush $canal
}

proc atender {canal endereco porta_remota} {
    global descricao
    fconfigure $canal -buffering line -translation lf
    puts $canal "@@ PRONTO $descricao"
    flush $canal
    fileevent $canal readable [list ler $canal]
}

socket -server atender -myaddr 127.0.0.1 $porta
vwait ::terminar

if {!$teste} {
    catch {device_unlock}
    catch {close_device}
}

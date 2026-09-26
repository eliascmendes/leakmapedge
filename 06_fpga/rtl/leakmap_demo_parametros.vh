// Gerado por 06_fpga/computador/demo_autonoma.py. Nao editar a mao.
// Constantes da demonstracao autonoma (rtl/leakmap_demo.v): gerador de sinais,
// conta da posicao e configuracao do detector, a mesma do modelo em Python.
localparam integer DEMO_N_AMOSTRAS       = 512;
localparam integer DEMO_AMOSTRA_EVENTO   = 150;
localparam integer DEMO_BASE             = 58000;
localparam integer DEMO_PASSO_QUEDA      = 50;
localparam integer DEMO_RAMPA            = 8;
localparam integer DEMO_SENSOR_A         = 40;
localparam integer DEMO_SENSOR_B         = 160;
localparam integer DEMO_AMOSTRAS_POR_M   = 135987;   // Q16
localparam integer DEMO_METROS_POR_AMOS  = 15792;   // Q16
localparam [15:0]  DEMO_SEMENTE_A        = 16'hACE1;
localparam [15:0]  DEMO_SEMENTE_B        = 16'h1D2F;
localparam [15:0]  DEMO_POLINOMIO        = 16'hB400;
localparam integer DEMO_AMOSTRA_FALHA    = 100;
localparam [15:0]  DEMO_SAUDE_CONGELADO  = 16'd32;   // so com ruido
localparam [15:0]  DEMO_SAUDE_MINIMO     = 16'd1;
localparam [15:0]  DEMO_SAUDE_MAXIMO     = 16'd65534;
localparam [15:0]  DEMO_SAUDE_SALTO      = 16'd32767;
localparam [31:0]  DEMO_CFG_COEF         = 32'd62390;
localparam [7:0]   DEMO_CFG_FRACAO       = 8'd16;
localparam [7:0]   DEMO_CFG_DESLOCA      = 8'd8;
localparam [7:0]   DEMO_CFG_N_CURTA      = 8'd6;
localparam [7:0]   DEMO_CFG_N_GUARDA     = 8'd3;
localparam [7:0]   DEMO_CFG_N_LONGA      = 8'd30;
localparam [15:0]  DEMO_CFG_LIMIAR       = 16'd12;
localparam [15:0]  DEMO_CFG_K2           = 16'd9;
localparam [31:0]  DEMO_CFG_PISO         = 32'd6252;
localparam [31:0]  DEMO_CFG_PISO_ENERGIA = 32'd3257292;
localparam integer DEMO_PERIODO_S_NS     = 401306;   // periodo de amostragem, em ns

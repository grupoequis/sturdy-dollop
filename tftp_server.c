#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <time.h>
#include <fcntl.h>

#define RRQ 1
#define WRQ 2
#define DATA 3
#define ACK 4
#define ERROR 5

#define DEFAULT_PORT 69

const char *errors[8] =
{ "Not defined, see error message (if any)."
, "File not found."
, "Access violation."
, "Disk full or allocation exceeded."
, "Illegal TFTP operation."
, "Unknown transfer ID."
, "File already exists."
, "No such user."
};

int create_socket(struct sockaddr_in* addr){
    unsigned int TID = rand() % 65535;
    bzero((char *) addr, sizeof(struct sockaddr_in));
    addr->sin_family = AF_INET;
    addr->sin_port = htons(TID);
    addr->sin_addr.s_addr = INADDR_ANY;
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    return sock;
}

void send_error(int errtype, int sv_socket, struct sockaddr* cl_addr, socklen_t cl_len){
    unsigned short header[2];
    char buff[512];
    bzero(buff, 512);
    header[0] = htons(ERROR);
    header[1] = htons(errtype);
    memcpy(buff, header, 4);
    strcpy(buff + 4, errors[errtype]);
    printf("Error code %d: %s\n", errtype, errors[errtype]);
    sendto(sv_socket, buff, 5 + strlen(errors[errtype]), 0, cl_addr, cl_len);
}

void mk_datah(char* buff, unsigned short i){
    unsigned short header[2];
    header[0] = htons(DATA);
    header[1] = htons(i);
    memcpy(buff, header, 4);
}

void* ack_packet(unsigned short blockn){
    unsigned short* packet = (unsigned short*) malloc(4*sizeof(char));
    packet[0] = htons(ACK);
    packet[1] = htons(blockn);
    char * pk = (char *) packet;
    return (void*) packet;
}

unsigned short ack_num(char* packet){
    return (unsigned short) ntohs(*((unsigned short*) packet + 1));
}

char* get_filename(char* packet, char* filename){
    return strcpy(filename, &packet[2]);
}

unsigned short get_opcode(char* packet){
    return ntohs(*((unsigned short *) packet));
}

int fexist(char* filename){
    if(access(filename, F_OK ) != -1 ) {
        return 1;
    }else{
        return 0;
    }
}

int main(int argc, char const *argv[]) {
    srand(time(NULL));
    struct sockaddr_in sv_addr, cl_addr;
    int sv_socket, cl_socket;
    socklen_t cl_len;
    sv_socket = socket(AF_INET, SOCK_DGRAM, 0);
    if(sv_socket < 0){
        printf("Error opening socket.\n");
        exit(1);
    }
    /* Creating and binding initial server address*/
    bzero((char *) &sv_addr, sizeof(sv_addr));
    sv_addr.sin_family = AF_INET;
    sv_addr.sin_port = htons(DEFAULT_PORT);
    sv_addr.sin_addr.s_addr = INADDR_ANY;
    if (bind(sv_socket, (struct sockaddr *) &sv_addr, sizeof(sv_addr)) < 0)
        printf("Error on binding\n");

    char buff[1024];
    bzero(buff, 1024);
    char filename[512];
    //
    printf("Server started.\n");
    while(1){
        printf("Waiting for RQ.\n");
        /*****************************************/
        int packet_len;
        bzero(&cl_addr, sizeof(cl_addr));
        cl_len = sizeof(cl_addr);
        packet_len = recvfrom(sv_socket, buff, 1024, 0, (struct sockaddr *) &cl_addr, &cl_len);
        if(packet_len < 0){
            printf("Error reading from socket\n");
            exit(1);
        }
        short opcode = get_opcode(buff);
        /*****************************************/
        if(opcode == WRQ){
            printf("Beggining WRQ.\n");
            get_filename(buff, filename);
            if(fexist(filename)){
                send_error(6, sv_socket, (struct sockaddr *) &cl_addr, cl_len);
                continue;
            }
            FILE * file = fopen(filename, "wb+");
            char data[512];
            unsigned short i = 1;
            int set = 0;
            struct sockaddr_in conn_addr;
            int conn_socket = create_socket(&conn_addr);
            if(bind(conn_socket, (struct sockaddr *) &conn_addr, sizeof(conn_addr)) < 0)
                printf("Error on binding\n");
            int ret = sendto(conn_socket, ack_packet(0), 4, 0, (struct sockaddr *) &cl_addr, cl_len);
            while(1){
                struct timeval tv;
                tv.tv_sec = 3;
                tv.tv_usec = 0;
                if (setsockopt(conn_socket, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv)) < 0) {
                    perror("Error setting timeout.");
                    exit(0);
                }
                for(int j = 0; j < 8; j++){
                    packet_len = recvfrom(conn_socket, buff, 1024, 0, (struct sockaddr *) &cl_addr, &cl_len);
                    if(packet_len > 0){
                        unsigned short num;
                        memcpy(&num, buff+2, 2);
                        num = htons(num);
                        if(num != i){
                            sendto(conn_socket, ack_packet(i-1), 4, 0, (struct sockaddr *) &cl_addr, cl_len);
                            continue;
                        }
                        break;
                    }
                    printf("Timed out, retrying.\n");
                }
                if(packet_len < 0){
                    printf("Timed out. Transfer cancelled.\n");
                    break;
                }
                if(get_opcode(buff) == DATA){
                    if(packet_len < 516){
                        int set = 1;
                        fwrite(buff + 4, packet_len - 4, 1, file);
                        sendto(conn_socket, ack_packet(i++), 4, 0, (struct sockaddr *) &cl_addr, cl_len);
                        break;
                    }
                    fwrite(buff + 4, packet_len - 4, 1, file);
                    sendto(conn_socket, ack_packet(i++), 4, 0, (struct sockaddr *) &cl_addr, cl_len);
                }
            }
            if(!set){
                fclose(file);
                continue;
            }
            printf("WRQ complete.\n");
            fclose(file);
        /*****************************************/
        }else if(opcode == RRQ){
            printf("Beggining RRQ.\n");
            get_filename(buff, filename);
            FILE * file;
            if(!fexist(filename)){
                send_error(1, sv_socket,  (struct sockaddr *) &cl_addr, cl_len);
                continue;
            }
            file = fopen(filename, "rb");
            char data[516];
            char set = 0;
            unsigned short i = 1;
            cl_len = sizeof(cl_addr);
            struct sockaddr_in conn_addr;
            int conn_socket = create_socket(&conn_addr);
            if(bind(conn_socket, (struct sockaddr *) &conn_addr, sizeof(conn_addr)) < 0){
                printf("Error on binding\n");
                exit(1);
            }
            struct timeval tv;
            tv.tv_sec = 3;
            tv.tv_usec = 0;
            if (setsockopt(conn_socket, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv)) < 0) {
                perror("Error setting timeout.");
                exit(0);
            }
            while(!set){
                mk_datah(data, i);
                size_t len = fread(&data[4], 1, 512, file);
                while(1){
                    sendto(conn_socket, data, len + 4, 0, (struct sockaddr *) &cl_addr, cl_len);
                    if(len < 512){
                        set = 1;
                        break;
                    }
                    for(int j = 0; j < 8; j++){
                        packet_len = recvfrom(conn_socket, buff, 1024, 0, (struct sockaddr *) &cl_addr, &cl_len);
                        if(packet_len > 0){
                            if(get_opcode(buff) == ACK && ack_num(buff) == i){
                                i++;
                                break;
                            }
                            j--;
                            continue;
                        }
                        printf("Timed out, retrying.\n");
                        if(packet_len < 0){
                            printf("Timed out. Transfer cancelled.\n");
                            break;
                        }
                    }
                    if(!set){
                        break;
                    }
                }
            }
            set = 0;
            printf("RRQ complete.\n");
            fclose(file);
        }else{
            send_error(5, sv_socket, (struct sockaddr *) &cl_addr, cl_len);
        }
        /*****************************************/
    }
    close(sv_socket);
    return 0;
}
